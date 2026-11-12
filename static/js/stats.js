/*
 * stats.js: the Stats page. Data from /api/stats; charts drawn with Chart.js.
 *
 * Chart colors are the two validated "series" colors in app.css (blue = series 1,
 * orange = series 2). They passed contrast and colorblind-separation checks on
 * all three themes. Text uses the normal ink colors, never the series color.
 * Charts redraw when you switch themes.
 */

let statsData = null;
const charts = {};

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** "#5B5560" + 0.25 -> "rgba(91, 85, 96, 0.25)" (canvas needs plain colors). */
function fade(hex, alpha) {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** Shared look: thin bars with rounded ends, faint grid, theme text colors, hover tooltips. */
function baseOptions({ horizontal = false, legend = false } = {}) {
  const ink = token("--ink"), muted = token("--muted");
  const grid = fade(muted, 0.25);   // faint gridlines
  Chart.defaults.font.family = '"Atkinson Hyperlegible", system-ui, sans-serif';
  Chart.defaults.color = muted;
  return {
    indexAxis: horizontal ? "y" : "x",
    responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: legend, labels: { color: ink, usePointStyle: true, pointStyle: "rectRounded", boxWidth: 10 } },
      tooltip: { backgroundColor: token("--card"), titleColor: ink, bodyColor: ink, borderColor: token("--line"),
                 borderWidth: 2, padding: 10, cornerRadius: 10, usePointStyle: true },
    },
    scales: {
      [horizontal ? "x" : "y"]: { beginAtZero: true, ticks: { precision: 0, color: muted }, grid: { color: grid }, border: { display: false } },
      [horizontal ? "y" : "x"]: { ticks: { color: ink }, grid: { display: false }, border: { color: muted } },
    },
  };
}

function bar(label, data, colorToken) {
  return { label, data, backgroundColor: token(colorToken), borderRadius: 4, borderSkipped: "start",
           maxBarThickness: 28, categoryPercentage: 0.7, barPercentage: 0.9 };
}

function table(el, headers, rows) {
  el.replaceChildren(h("table", { class: "budget-table" },
    h("thead", {}, h("tr", {}, headers.map((x) => h("th", {}, x)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c)))))));
}

function draw() {
  const d = statsData;
  Object.values(charts).forEach((c) => c.destroy());

  // Tiles: single headline numbers don't need a chart.
  fill(document.getElementById("stat-tiles"),
    h("div", { class: "card stat" }, h("strong", {}, d.sent), h("span", {}, "reached Sent")),
    h("div", { class: "card stat", title: "Of everything that reached Sent: share that got a reply or reached Talking" },
      h("strong", {}, d.response_rate === null ? "–" : `${d.response_rate}%`), h("span", {}, `response rate (${d.responded} of ${d.sent})`)),
    h("div", { class: "card stat", title: "Days from moving a card to Sent until it reached Talking" },
      h("strong", {}, d.avg_days_to_hear_back ?? "–"), h("span", {}, d.waits_measured ? `avg. days to hear back (${d.waits_measured} measured)` : "avg. days to hear back (none yet)")),
    h("div", { class: "card stat", title: "Total actual minutes ÷ total estimated minutes, last finished tasks" },
      h("strong", {}, d.estimate_ratio === null ? "–" : `${d.estimate_ratio}×`), h("span", {}, "actual vs. estimated time")));

  charts.funnel = new Chart(document.getElementById("funnel-chart"), {
    type: "bar",
    data: { labels: d.funnel.map((f) => f.label), datasets: [bar("Opportunities", d.funnel.map((f) => f.count), "--series-1")] },
    options: baseOptions({ horizontal: true }),
  });
  table(document.getElementById("funnel-table"), ["Stage", "Reached"], d.funnel.map((f) => [f.label, f.count]));

  const weekLabels = d.weeks.map((w) => fmtDate(w.week, { month: "short", day: "numeric" }));
  charts.weekly = new Chart(document.getElementById("weekly-chart"), {
    type: "bar",
    data: { labels: weekLabels, datasets: [bar("Applications", d.weeks.map((w) => w.applications), "--series-1"),
                                           bar("Outreach", d.weeks.map((w) => w.outreach), "--series-2")] },
    options: baseOptions({ legend: true }),
  });
  table(document.getElementById("weekly-table"), ["Week of", "Applications", "Outreach", "Focus hours", "Tasks done"],
        d.weeks.map((w, i) => [weekLabels[i], w.applications, w.outreach, w.focus_hours, w.tasks_done]));

  const est = d.estimates;
  if (d.estimate_ratio !== null) {
    const pct = Math.round(Math.abs(d.estimate_ratio - 1) * 100);
    document.getElementById("estimate-caption").textContent =
      `Blue is what you estimated, orange is what you logged, for your last ${est.length} finished tasks. ` +
      (d.estimate_ratio > 1.1 ? `You take about ${pct}% longer than you plan, so pad your estimates.`
        : d.estimate_ratio < 0.9 ? `You finish about ${pct}% faster than you plan.` : "Your estimates are close to reality.");
  }
  const short = (s) => (s.length > 22 ? s.slice(0, 21) + "…" : s);
  charts.estimate = new Chart(document.getElementById("estimate-chart"), {
    type: "bar",
    data: { labels: est.map((e) => short(e.title)),
            datasets: [bar("Estimated (min)", est.map((e) => e.est_min), "--series-1"),
                       bar("Actual (min)", est.map((e) => e.actual_min), "--series-2")] },
    options: { ...baseOptions({ legend: true }),
               plugins: { ...baseOptions({ legend: true }).plugins,
                          tooltip: { ...baseOptions().plugins.tooltip, callbacks: { title: (items) => est[items[0].dataIndex].title } } } },
  });
  table(document.getElementById("estimate-table"), ["Task", "Estimated", "Actual"],
        est.map((e) => [e.title, fmtMinutes(e.est_min), fmtMinutes(e.actual_min)]));
  if (!est.length) {
    document.getElementById("estimate-caption").textContent =
      "No data yet: finish tasks that have an estimate and logged time (the focus timer logs it for you).";
  }
}

async function load() {
  statsData = await api("GET", "/api/stats");
  draw();
}

document.addEventListener("lp:theme", () => statsData && draw());
load();
