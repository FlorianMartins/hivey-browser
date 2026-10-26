# Tests

Two scripts check a built browser. Both run on Windows and Linux: on the
build host for Linux, on a GitHub runner for Windows
(`.github/workflows/windows-smoke.yml`), before every release.

## No request at startup

`startup_requests.py` starts the browser on a fresh profile (first-run tab
included) with a NetLog capture, lets it idle for a minute, and lists every
request and DNS lookup. It fails on anything besides browser-internal URLs
and the encrypted DNS resolver's probe (`dns.quad9.net`).

```bash
xvfb-run -a python3 tests/startup_requests.py out/Linux/chrome --keep out/
python3 tests/startup_requests.py "%LOCALAPPDATA%\Hivey\Browser\Application\chrome.exe"
```

## Privacy checks

`cdp_checks.py` drives a running browser over the DevTools protocol and
measures each protection instead of trusting a setting:

| Check | How |
| --- | --- |
| Referrer cut to the origin | a page asking for `unsafe-url` fetches from another local origin, which echoes the `Referer` it got |
| Audio noise | samples written to an `AudioBuffer` read back slightly changed |
| `hardwareConcurrency` | at most 8 |
| No Topics, no fenced frames | `document.browsingTopics`, `HTMLFencedFrameElement` |
| Cosmetic filtering | ad slots on a local test page are hidden |
| Version shown to the web | client hints carry the upstream Chromium version |
| Bundled blocker running | the uBlock Origin Lite service worker is listed |
| Hivey Studio | `chrome://hivey` loads, its live usage gauges update |
| Tracking parameters | `fbclid`/`utm_source` removed from a navigation |
| Global Privacy Control | `navigator.globalPrivacyControl` and the `Sec-GPC: 1` header echoed by httpbin.org |
| WebGL GPU hidden | `WEBGL_debug_renderer_info` values (a VM without a GPU reports "no webgl") |
| Canvas noise | the same drawing hashes differently on two page loads |
| Content blocker | an ad script and a tracker fail to load, a normal request succeeds |
| HTTPS-Only | a plain-HTTP site does not load directly |

```bash
chrome --remote-debugging-port=9222 --user-data-dir=/tmp/p --no-first-run &
python3 tests/cdp_checks.py http://127.0.0.1:9222 --shots shots/   # --offline: local checks only
```
