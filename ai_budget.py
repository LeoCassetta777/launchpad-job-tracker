"""AI spending: log what every AI call costs, and stop at a monthly cap.

    check(conn, override=False)    call BEFORE asking the AI; raises BudgetError at the cap
    record(conn, feature, model, usage)   call AFTER; saves tokens + dollars, returns the cost
    summary(conn)                  numbers for the Settings meter

Prices are per million tokens, from Anthropic's pricing page
(https://platform.claude.com/docs/en/about-claude/pricing), checked 2026-11-09.
If Anthropic changes prices, update PRICES. The meter is an estimate from those
prices; your Anthropic Console billing page is the official number.

Overrides, two ways:
  * "Run anyway" on a single request (the browser re-sends it with override_cap).
  * "Allow AI past the cap for the rest of this month" in Settings.
"""
import config
import settings_store

# model: (input $/MTok, output $/MTok, cache-read multiplier)
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.10),
    "claude-sonnet-5-5": (2.00, 10.00, 0.05),
    "claude-sonnet-5": (2.00, 10.00, 0.10),     # the agent's automatic fallback if Sonnet 5.5 declines
}
HAIKU_LONG_PROMPT = 100_000                 # Haiku 5.5 prompts over this cost more:
HAIKU_LONG_PRICES = (0.50, 2.50, 0.10)      # $0.50 in / $2.50 out
FALLBACK_PRICES = (2.00, 10.00, 0.05)       # unknown model: assume Sonnet prices (safer to overestimate)


class BudgetError(Exception):
    """The monthly cap is reached. The API turns this into a "run anyway?" question."""


def _month():
    return config.now().strftime("%Y-%m")


def cost_of(model, input_tokens, output_tokens, cache_write=0, cache_read=0):
    """Dollar cost of one request. Thinking tokens are already counted inside output_tokens."""
    in_price, out_price, read_mult = PRICES.get(model, FALLBACK_PRICES)
    if model == "claude-haiku-5-5" and input_tokens + cache_write + cache_read > HAIKU_LONG_PROMPT:
        in_price, out_price, read_mult = HAIKU_LONG_PRICES
    dollars = (input_tokens * in_price
               + cache_write * in_price * 1.25      # 5-minute cache writes cost 1.25x input
               + cache_read * in_price * read_mult
               + output_tokens * out_price) / 1_000_000
    return round(dollars, 6)


def month_spent(conn, month=None):
    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM ai_usage WHERE substr(created_at, 1, 7) = ?",
                       (month or _month(),)).fetchone()
    return round(row[0], 6)


def _cap_and_override(conn):
    settings = settings_store.get_all(conn)
    cap = float(settings["ai_monthly_cap"])
    overridden = settings["ai_cap_override_month"] == _month()
    return cap, overridden


def check(conn, override=False):
    """Raise BudgetError if this month's spending has reached the cap (unless overridden)."""
    cap, overridden = _cap_and_override(conn)
    spent = month_spent(conn)
    if spent >= cap and not (override or overridden):
        raise BudgetError(f"You've reached your monthly AI cap: ${spent:.2f} of ${cap:.2f} spent in "
                          f"{config.now():%B}.")


def record(conn, feature, model, usage, overridden=False):
    """Save one call's tokens and cost. `usage` is the SDK's response.usage object."""
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cost = cost_of(model, usage.input_tokens, usage.output_tokens, cache_write, cache_read)
    # Web searches (Discover's LinkedIn/Indeed sweep) cost $10 per 1,000 on top of tokens.
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    cost = round(cost + searches * 0.01, 6)
    conn.execute(
        "INSERT INTO ai_usage (created_at, feature, model, input_tokens, output_tokens, cache_write_tokens, "
        "cache_read_tokens, cost_usd, over_cap) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (config.now_str(), feature, model, usage.input_tokens, usage.output_tokens, cache_write, cache_read,
         cost, 1 if overridden else 0))
    conn.commit()
    return cost


def summary(conn):
    """Everything the Settings meter shows."""
    cap, overridden = _cap_and_override(conn)
    month = _month()
    spent = month_spent(conn, month)
    by_feature = [dict(r) for r in conn.execute(
        "SELECT feature, model, COUNT(*) AS calls, SUM(cost_usd) AS cost, "
        "SUM(input_tokens + cache_write_tokens + cache_read_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens "
        "FROM ai_usage WHERE substr(created_at, 1, 7) = ? GROUP BY feature, model ORDER BY cost DESC", (month,)).fetchall()]
    all_time = conn.execute("SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) FROM ai_usage").fetchone()
    return {
        "month": month, "month_label": f"{config.now():%B %Y}", "spent": round(spent, 4), "cap": cap,
        "percent": min(100, round(100 * spent / cap)) if cap else 100,
        "overridden": overridden, "over_cap": spent >= cap,
        "calls": sum(f["calls"] for f in by_feature), "by_feature": by_feature,
        "all_time_spent": round(all_time[0], 4), "all_time_calls": all_time[1],
    }
