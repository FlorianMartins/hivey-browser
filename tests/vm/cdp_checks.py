#!/usr/bin/env python3
"""Check Hivey Browser's privacy defaults on a running browser, over DevTools.

    cdp_checks.py [http://127.0.0.1:9222] [--shots DIR]

Start the browser with --remote-debugging-port=9222 (on Windows, reach it
through an SSH tunnel). Every check measures behavior instead of trusting a
setting, and the script exits non-zero if one fails.
"""
import base64
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

BASE = next((a for a in sys.argv[1:] if a.startswith('http')), 'http://127.0.0.1:9222')
SHOTS = Path(sys.argv[sys.argv.index('--shots') + 1]) if '--shots' in sys.argv else None


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

p = Page()
try:
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

    # 4. Built-in blocker: a well-known ad script must not load.
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
                      ('settings-security', 'chrome://settings/security'),
                      ('settings-ads', 'chrome://settings/content/ads')):
        p.goto(url, settle=2.5)
        p.shot(name)
finally:
    p.close()

failed = [r for r in results if not r[1]]
print(f'\n{len(results) - len(failed)}/{len(results)} checks passed')
sys.exit(1 if failed else 0)
