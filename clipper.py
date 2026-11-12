"""The "Send to Launchpad" bookmarklet.

A bookmarklet is a favorite whose address is JavaScript instead of a web page.
Clicking it on a job posting runs the script below on that page. The script
grabs the page address, the title, and your highlighted text (or the whole page
text if nothing is highlighted), then hands it to Launchpad in a new tab.

Why not put the text in the URL? Long postings would blow past URL length
limits. So it uses three methods, in order:

  1. Form POST (main path). The script builds a hidden form and submits it to
     <APP>/clip in a new tab. A POST body has no practical size limit.
  2. postMessage (backup). Some sites forbid forms that submit to other
     addresses (a "form-action" security policy). The browser reports that as a
     "securitypolicyviolation" event. When we see it, we open <APP>/clip
     ourselves; when that tab says "launchpad-ready", we pass it the data
     directly, browser tab to browser tab.
  3. Clipboard (last resort). If the new tab is blocked too, the text is copied
     and you paste it into Launchpad's job-posting box.

Nothing is saved when /clip opens. It only fills in the paste-a-posting box,
and the AI runs when you click the button.
"""
from urllib.parse import quote

# Written without // comments, because the code gets squeezed onto one line.
_SOURCE = r"""
(function () {
  var app = "__APP__";
  var sel = String(window.getSelection() || "").trim();
  var data = {
    url: location.href,
    title: document.title,
    text: (sel || (document.body && document.body.innerText) || "").slice(0, 60000),
    selected: sel ? "1" : ""
  };
  var switched = false;

  function viaClipboard() {
    var all = data.url + "\n" + data.title + "\n\n" + data.text;
    var msg = "Launchpad couldn't open from this site, so the posting text was copied. Open Launchpad and paste it into the job-posting box.";
    if (navigator.clipboard) {
      navigator.clipboard.writeText(all).then(function () { alert(msg); }, function () {
        alert("Launchpad couldn't capture this page. Copy the posting text yourself and paste it into Launchpad.");
      });
    } else {
      alert("Launchpad couldn't capture this page. Copy the posting text yourself and paste it into Launchpad.");
    }
  }

  function viaMessage() {
    if (switched) return;
    switched = true;
    var win = window.open(app + "/clip", "_blank");
    if (!win) { viaClipboard(); return; }
    var sent = false;
    window.addEventListener("message", function (e) {
      if (!sent && e.origin === app && e.source === win && e.data === "launchpad-ready") {
        sent = true;
        win.postMessage({ type: "launchpad-clip", clip: data }, app);
      }
    });
    setTimeout(function () { if (!sent) viaClipboard(); }, 6000);
  }

  document.addEventListener("securitypolicyviolation", function (e) {
    if (/form-action/.test(e.effectiveDirective || e.violatedDirective || "")) viaMessage();
  });

  var form = document.createElement("form");
  form.method = "POST";
  form.action = app + "/clip";
  form.target = "_blank";
  form.acceptCharset = "UTF-8";
  form.style.display = "none";
  Object.keys(data).forEach(function (key) {
    var field = document.createElement("textarea");
    field.name = key;
    field.value = data[key];
    form.appendChild(field);
  });
  document.body.appendChild(form);
  try { form.submit(); } catch (err) { viaMessage(); }
  setTimeout(function () { form.remove(); }, 1000);
})();
"""


def bookmarklet_href(app_origin):
    """The javascript: address to save as a favorite, pointed at this Launchpad."""
    js = _SOURCE.replace("__APP__", app_origin.rstrip("/"))
    one_line = " ".join(line.strip() for line in js.strip().splitlines() if line.strip())
    return "javascript:" + quote(one_line, safe="(){}[];:,.=!&|+-*/<>'\"?_$")


def readable_source(app_origin):
    """The same script, formatted, for the Settings page's 'see the code' box."""
    return _SOURCE.replace("__APP__", app_origin.rstrip("/")).strip()
