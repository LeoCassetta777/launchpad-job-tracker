"""Small helpers for reading things from the web: download a URL safely, and turn HTML into text.

Used by discover.py (company career pages) and canvas_sync.py (Canvas feeds).

Safety rules for every download:
  * https only (no plain http, no file:// or other schemes)
  * never a computer on the home network or the Mac itself (blocks tricks like
    pointing a "feed" at http://127.0.0.1 to poke at local services)
  * a size limit and a timeout, so one bad site can't hang or flood the Mac
"""
import ipaddress
import json
import re
import socket
import ssl
import urllib.error
import urllib.request

import certifi
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

MAX_BYTES = 8 * 1024 * 1024          # 8 MB is plenty for a feed
BIG_BYTES = 40 * 1024 * 1024         # big companies' full job lists (with descriptions) can be 10-20 MB
TIMEOUT = 25                          # seconds
# Trusted certificate list from the certifi package. Python installed from python.org on a Mac
# ships without one, so https downloads failed there with CERTIFICATE_VERIFY_FAILED.
_TLS = ssl.create_default_context(cafile=certifi.where())
USER_AGENT = "Launchpad/1.0 (personal job-search tracker; one request per source a few times a day)"


class FetchError(Exception):
    """Something went wrong downloading; the message is safe to show in the app."""


def check_url(url):
    """Raise FetchError unless `url` is https and points at a public internet address."""
    parts = urlparse(url or "")
    if parts.scheme != "https" or not parts.hostname:
        raise FetchError("Links must start with https://")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, 443)}
    except socket.gaierror:
        raise FetchError(f"Couldn't find the site {parts.hostname}.")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise FetchError(f"{parts.hostname} points at a private address, so Launchpad won't read it.")


def is_web_link(url):
    """True for http(s) addresses (what we allow as links on cards)."""
    return bool(re.match(r"https?://[^\s]+$", url or ""))


def get(url, accept="*/*", max_bytes=MAX_BYTES):
    """Download `url` and return the bytes. Raises FetchError with a readable message."""
    check_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=_TLS) as response:
            check_url(response.geturl())            # if it redirected, the new place must be safe too
            data = response.read(max_bytes + 1)
    except urllib.error.HTTPError as e:
        hint = {401: " (it needs a login)", 403: " (access denied)", 404: " (not found: check the link)"}.get(e.code, "")
        raise FetchError(f"{urlparse(url).hostname} answered {e.code}{hint}.")
    except (urllib.error.URLError, OSError) as e:
        raise FetchError(f"Couldn't reach {urlparse(url).hostname}: {getattr(e, 'reason', e)}")
    if len(data) > max_bytes:
        raise FetchError(f"{urlparse(url).hostname} sent more data than expected, so it was skipped.")
    return data


def get_json(url, max_bytes=MAX_BYTES):
    try:
        return json.loads(get(url, accept="application/json", max_bytes=max_bytes))
    except ValueError:
        raise FetchError(f"{urlparse(url).hostname} didn't send readable data.")


# ---------------------------------------------------------------- HTML -> text

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
               "section", "article", "header", "footer", "table", "blockquote", "hr"}


class _TextAndLinks(HTMLParser):
    """Collects readable text, plus every link as (address, link text)."""

    def __init__(self, mark_links=False):
        super().__init__(convert_charrefs=True)
        self.mark_links = mark_links    # put a [L3]-style marker after each link's text
        self.parts, self.links = [], []
        self._skip = 0                  # inside <script>/<style>
        self._href, self._link_text = None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("• ")
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._link_text).split())))
            if self.mark_links:
                self.parts.append(f" [L{len(self.links)}]")
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        self.parts.append(data)
        if self._href is not None:
            self._link_text.append(data)


def html_to_text(html, with_links=False, mark_links=False):
    """Readable plain text from HTML. with_links=True also returns [(href, text), ...].

    mark_links=True writes [L1], [L2], ... after each link's text, numbered in the same
    order as the returned list, so the AI can say which link belongs to which listing
    without ever writing (or inventing) an address itself.
    """
    parser = _TextAndLinks(mark_links)
    parser.feed(html or "")
    parser.close()
    text = "".join(parser.parts)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*(\n\s*)+", "\n\n", text)      # at most one blank line in a row
    text = "\n".join(line.strip() for line in text.splitlines()).strip()
    return (text, parser.links) if with_links else text


def unescape_html(text):
    """Greenhouse sends its posting HTML with the tags escaped (&lt;p&gt;); this undoes that."""
    return unescape(text or "")
