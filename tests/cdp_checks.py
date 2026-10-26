#!/usr/bin/env python3
"""Check Hivey Browser's privacy defaults on a running browser, over DevTools.

    cdp_checks.py [http://127.0.0.1:9222] [--shots DIR] [--offline]

Start the browser with --remote-debugging-port=9222 (Windows or Linux; CI
runs it on both). Every check measures behavior instead of trusting a
setting, and the script exits non-zero if one fails. Checks that need the
internet (public test sites, the ad blocker on real ad hosts) are skipped
with --offline; the others use a small local server with two origins
(localhost and 127.0.0.1).
"""
import base64
import hashlib
import http.server
import json
import socketserver
import sys
import threading
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

BASE = next((a for a in sys.argv[1:] if a.startswith('http')), 'http://127.0.0.1:9222')
SHOTS = Path(sys.argv[sys.argv.index('--shots') + 1]) if '--shots' in sys.argv else None
OFFLINE = '--offline' in sys.argv
SHIELD_ID = 'dijgmkdjplmconokheconjjfkplefhbe'  # bundled uBlock Origin Lite


class LocalSite(http.server.BaseHTTPRequestHandler):
    """/page: a page that asks for full referrers and holds an ad slot.
    /echo: returns the Referer header it got (CORS-enabled)."""

    def do_GET(self):
        if self.path.startswith('/echo'):
            body = json.dumps({'referer': self.headers.get('Referer')}).encode()
            ctype = 'application/json'
        else:
            body = b"""<!doctype html><meta name="referrer" content="unsafe-url">
<title>Hivey test page</title><p>Test page</p>
<ins class="adsbygoogle" style="display:block;width:300px;height:250px">ad</ins>
<div id="ad-banner" class="ad-banner" style="width:300px;height:90px">ad</div>"""
            ctype = 'text/html'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def serve():
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), LocalSite)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


PORT = serve()


class Page:
    def __init__(self):
        req = urllib.request.Request(f'{BASE}/json/new?about:blank', method='PUT')
        target = json.load(urllib.request.urlopen(req))
        self.id = target['id']
        self.ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=60,
                                              suppress_origin=True)
        self.n = 0
        self.events = []
        self.call('Page.enable')
        self.call('Runtime.enable')
        self.call('Log.enable')

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({'id': self.n, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self.n:
                if 'error' in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get('result', {})
            self.events.append(msg)

    def goto(self, url, settle=2.0):
        self.events.clear()
        self.call('Page.navigate', url=url)
        deadline = time.time() + 45
        while time.time() < deadline:
            if any(e.get('method') == 'Page.loadEventFired' for e in self.events):
                break
            try:
                self.events.append(json.loads(self.ws.recv()))
            except websocket.WebSocketTimeoutException:
                break
        time.sleep(settle)
        return self.eval('location.href')

    def eval(self, expr):
        r = self.call('Runtime.evaluate', expression=expr, awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in r:
            return f"EXCEPTION: {r['exceptionDetails'].get('exception', {}).get('description', r['exceptionDetails'])}"
        return r['result'].get('value')

    def shot(self, name):
        if not SHOTS:
            return
        SHOTS.mkdir(parents=True, exist_ok=True)
        data = self.call('Page.captureScreenshot', format='png')['data']
        (SHOTS / f'{name}.png').write_bytes(base64.b64decode(data))

    def close(self):
        self.ws.close()
        urllib.request.urlopen(f'{BASE}/json/close/{self.id}')


results = []


def check(name, ok, detail):
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


CANVAS_HASH = """(() => { const c = document.createElement('canvas'); c.width = 220; c.height = 40;
  const x = c.getContext('2d'); x.textBaseline = 'top'; x.font = '16px Arial';
  x.fillStyle = '#f60'; x.fillRect(10, 1, 62, 20); x.fillStyle = '#069';
  x.fillText('Hivey fingerprint test', 2, 15); return c.toDataURL(); })()"""

AUDIO_NOISE = """(() => { const ctx = new OfflineAudioContext(1, 64, 44100);
  const b = ctx.createBuffer(1, 64, 44100); const src = new Float32Array(64).map((_, i) => Math.sin(i / 3) / 2);
  b.copyToChannel(src, 0); const out = b.getChannelData(0); let diff = 0;
  for (let i = 0; i < 64; i++) diff = Math.max(diff, Math.abs(out[i] - src[i]));
  return diff; })()"""

p = Page()
try:
    # 0. Local checks (no internet needed).
    p.goto(f'http://localhost:{PORT}/page?secret=1', settle=4)
    ref = p.eval(f"fetch('http://127.0.0.1:{PORT}/echo').then(r => r.json()).then(j => j.referer)")
    check('Cross-origin referrer cut to the origin', ref == f'http://localhost:{PORT}/',
          f'page asks for unsafe-url, the other origin got Referer: {ref}')
    diff = p.eval(AUDIO_NOISE)
    check('Audio fingerprint noise', isinstance(diff, (int, float)) and 0 < diff < 1e-5,
          f'max change of AudioBuffer samples = {diff}')
    cores = p.eval('navigator.hardwareConcurrency')
    check('hardwareConcurrency capped', isinstance(cores, int) and cores <= 8, f'navigator.hardwareConcurrency = {cores}')
    topics = p.eval("typeof document.browsingTopics === 'function' ? "
                    "document.browsingTopics().then(() => 'available', e => 'refused: ' + e.name) : 'absent'")
    check('Topics API off', topics != 'available', f'document.browsingTopics: {topics}')
    fenced = p.eval("'HTMLFencedFrameElement' in window")
    check('Fenced frames off', fenced is False, f'HTMLFencedFrameElement in window = {fenced}')
    hidden = p.eval("""(() => { const s = ['.adsbygoogle', '#ad-banner'].map(q => document.querySelector(q));
      return s.map(e => e && (getComputedStyle(e).display === 'none' || e.offsetHeight === 0)); })()""")
    check('Cosmetic filtering (ad slots hidden)', hidden == [True, True], f'.adsbygoogle, #ad-banner hidden = {hidden}')
    p.shot('local-test-page')
    full = p.eval("navigator.userAgentData.getHighEntropyValues(['fullVersionList'])"
                  ".then(v => v.fullVersionList.map(b => b.version).join(' '))")
    check('Upstream version shown to the web', '.' in str(full) and
          all(int(v.split('.')[-1]) < 100 or v.endswith('.0.0.0') for v in str(full).split()),
          f'fullVersionList versions: {full}')
    targets = json.load(urllib.request.urlopen(f'{BASE}/json/list'))
    shield = [t for t in targets if SHIELD_ID in t.get('url', '')]
    check('Hivey Shield (uBlock Origin Lite) running', bool(shield),
          shield[0]['url'] if shield else 'no target from the bundled extension')
    p.goto('chrome://hivey/', settle=3)
    nav = p.eval("document.querySelectorAll('.nav-item').length")
    check('Hivey Studio loads', nav == 6, f'{nav} sections in the navigation')
    p.shot('hivey-studio')
    p.goto('chrome://hivey/#resources', settle=4)
    gauge = p.eval("document.querySelector('#gauge-ram .gauge-value')?.textContent")
    check('Hivey Studio live usage', bool(gauge) and gauge != '–', f'memory gauge shows {gauge!r}')
    p.shot('hivey-studio-resources')

    if OFFLINE:
        raise SystemExit
    # 0b. Tracking parameters removed from navigations.
    url = p.goto('https://example.com/?fbclid=hivey-test&utm_source=hivey', settle=2)
    check('Tracking parameters removed', 'fbclid' not in url and 'utm_source' not in url, f'landed on {url}')

    # 1. Global Privacy Control: JS signal and HTTP header.
    p.goto('https://example.com/')
    check('GPC (navigator)', p.eval('navigator.globalPrivacyControl') is True,
          f"navigator.globalPrivacyControl = {p.eval('navigator.globalPrivacyControl')}")
    p.goto('https://httpbin.org/headers')
    body = p.eval('document.body.innerText') or ''
    check('GPC (Sec-GPC header)', '"Sec-Gpc": "1"' in body,
          'Sec-GPC: 1 sent' if '"Sec-Gpc": "1"' in body else body[:200])

    # 2. WebGL GPU info hidden.
    p.goto('https://example.com/')
    gpu = p.eval("""(() => { const g = document.createElement('canvas').getContext('webgl');
      if (!g) return 'no webgl'; const e = g.getExtension('WEBGL_debug_renderer_info');
      return e ? JSON.stringify([g.getParameter(e.UNMASKED_VENDOR_WEBGL),
                                 g.getParameter(e.UNMASKED_RENDERER_WEBGL)]) : 'no extension'; })()""")
    check('WebGL GPU hidden', gpu in ('[" "," "]', 'no extension', 'no webgl'), f'vendor/renderer = {gpu}')

    # 3. Canvas fingerprint changes between page loads.
    h1 = hashlib.sha256(str(p.eval(CANVAS_HASH)).encode()).hexdigest()[:12]
    p.goto('https://example.com/?reload')
    h2 = hashlib.sha256(str(p.eval(CANVAS_HASH)).encode()).hexdigest()[:12]
    check('Canvas fingerprint noise', h1 != h2, f'hash load 1 = {h1}, load 2 = {h2}')

    # 4. Content blocker: a well-known ad script must not load.
    blocked = p.eval("""new Promise(r => { const s = document.createElement('script');
      s.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?t=' + Date.now();
      s.onload = () => r('loaded'); s.onerror = () => r('blocked'); document.head.appendChild(s);
      setTimeout(() => r('timeout'), 15000); })""")
    tracker = p.eval("""fetch('https://www.google-analytics.com/analytics.js?t=' + Date.now(), {mode: 'no-cors'})
      .then(() => 'loaded').catch(() => 'blocked')""")
    control = p.eval("""fetch('https://example.org/?t=' + Date.now(), {mode: 'no-cors'})
      .then(() => 'loaded').catch(e => 'blocked: ' + e)""")
    check('Ad blocked (googlesyndication)', blocked == 'blocked', f'ad script {blocked}')
    check('Tracker blocked (google-analytics)', tracker == 'blocked', f'tracker {tracker}')
    check('Normal request allowed', control == 'loaded', f'example.org {control}')

    # 5. HTTPS-Only (strict): a plain HTTP site gets the warning page.
    url = p.goto('http://http.badssl.com/', settle=3)
    title = p.eval('document.title')
    interstitial = url.startswith('chrome-error://') or 'not secure' in str(title).lower() or \
        'connection' in str(p.eval('document.body.innerText'))[:400].lower()
    check('HTTPS-Only warning on HTTP site', interstitial, f'url={url} title={title!r}')
    p.shot('https-only-warning')

    # 6. Settings pages, for the record.
    for name, url in (('settings-search', 'chrome://settings/search'),
                      ('settings-performance', 'chrome://settings/performance'),
                      ('settings-security', 'chrome://settings/security')):
        p.goto(url, settle=2.5)
        p.shot(name)
except SystemExit:
    pass
finally:
    p.close()

failed = [r for r in results if not r[1]]
print(f'\n{len(results) - len(failed)}/{len(results)} checks passed')
sys.exit(1 if failed else 0)
