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
AI_ID = 'lkcmbmbhbkaihiiioilbfoamihehnhce'  # bundled Hivey AI sidebar
CYBER_ID = 'kcbcbfchhinjlnahaoehhnogalnjlefg'  # bundled Hivey Cyber
# Hivey Studio's state, as the page gets it from its handler.
STUDIO_STATE = "import('chrome://resources/js/cr.js').then(cr => cr.sendWithPromise('getState'))"


class LocalSite(http.server.BaseHTTPRequestHandler):
    """/page: a page that asks for full referrers and holds an ad slot.
    /echo: returns the Referer header it got (CORS-enabled)."""

    def do_GET(self):
        if self.path.startswith('/echo'):
            body = json.dumps({'referer': self.headers.get('Referer')}).encode()
            ctype = 'application/json'
        elif self.path.startswith('/blob'):
            body = b'0' * 400_000
            ctype = 'application/octet-stream'
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

    def drain(self, seconds):
        """Collect events for a while."""
        deadline = time.time() + seconds
        self.ws.settimeout(0.5)
        try:
            while time.time() < deadline:
                try:
                    self.events.append(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
        finally:
            self.ws.settimeout(60)

    def request_outcome(self, trigger_js, needle):
        """How the content blocker handled requests whose URL contains
        `needle`: 'blocked', 'neutralized' (redirected to a harmless
        surrogate inside the extension, as uBlock Origin does for ad and
        analytics libraries that pages depend on) or 'loaded'."""
        self.call('Network.enable')
        self.events.clear()
        self.eval(trigger_js)
        self.drain(6)
        ids = {e['params']['requestId'] for e in self.events
               if e.get('method') == 'Network.requestWillBeSent' and needle in e['params']['request']['url']}
        if not ids:
            return 'not requested'
        for e in self.events:
            params = e.get('params', {})
            if params.get('requestId') not in ids:
                continue
            if e.get('method') == 'Network.loadingFailed':
                error = params.get('errorText')
                return f'blocked ({error})' if error == 'net::ERR_BLOCKED_BY_CLIENT' else f'failed ({error})'
            if e.get('method') == 'Network.requestWillBeSent' and \
                    params['request']['url'].startswith('chrome-extension://'):
                return 'neutralized'
        return 'loaded'

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
    p.shot('local-test-page')
    # Fonts: an installed font outside the standard set must measure like the
    # fallback (hidden); a standard font must not (the measure works).
    widths = p.eval("""(() => { const c = document.createElement('canvas').getContext('2d');
      const w = f => { c.font = `40px ${f}`; return c.measureText('mmmmmmmmmmlli1WQ@').width; };
      const base = w('monospace');
      const probe = n => Math.abs(w(`"${n}", monospace`) - base) > 0.5;
      return {standard: ['DejaVu Serif', 'Georgia', 'Times New Roman'].some(probe),
              leaked: ['Bitstream Charter', 'Nimbus Sans', 'Nimbus Roman', 'C059', 'IPAGothic', 'Loma',
                       'Arial Unicode MS', 'Garamond', 'Futura', 'Helvetica Neue', 'Roboto', 'Open Sans']
                      .filter(probe)}; })()""")
    if isinstance(widths, dict) and widths.get('standard'):
        check('Installed fonts hidden', not widths['leaked'],
              f"non-standard fonts visible to the page: {widths['leaked'] or 'none'}")
    else:
        print(f'SKIP  Installed fonts hidden: no standard font to compare with ({widths})')
    full = p.eval("navigator.userAgentData.getHighEntropyValues(['fullVersionList'])"
                  ".then(v => v.fullVersionList.map(b => b.version).join(' '))")
    check('Upstream version shown to the web', '.' in str(full) and
          all(int(v.split('.')[-1]) < 100 or v.endswith('.0.0.0') for v in str(full).split()),
          f'fullVersionList versions: {full}')
    targets = json.load(urllib.request.urlopen(f'{BASE}/json/list'))
    shield = [t for t in targets if SHIELD_ID in t.get('url', '')]
    check('Hivey Shield (uBlock Origin Lite) running', bool(shield),
          shield[0]['url'] if shield else 'no target from the bundled extension')
    for name, ext_id in (('Hivey AI sidebar', AI_ID), ('Hivey Cyber', CYBER_ID)):
        running = [t for t in targets if ext_id in t.get('url', '')]
        check(f'{name} running', bool(running), running[0]['url'] if running else 'no target from the bundled extension')

    # The AI sidebar reads a page only when invoked on it: its site access is
    # "on click", the AI providers' API hosts stay granted.
    p.goto('chrome://extensions/', settle=2)
    access = p.eval(f"""chrome.developerPrivate.getExtensionInfo('{AI_ID}').then(i => {{
      const h = i.permissions.runtimeHostPermissions;
      return h ? {{access: h.hostAccess, granted: h.hosts.filter(x => x.granted).map(x => x.host)}} : null; }})""")
    check('Hivey AI site access on click', isinstance(access, dict) and access['access'] != 'ON_ALL_SITES' and
          any('api.anthropic.com' in host for host in access['granted']), f'runtime host permissions: {access}')
    # The security tools' popup.
    p.goto(f'chrome-extension://{CYBER_ID}/popup.html', settle=1.5)
    tools = p.eval("document.querySelectorAll('.tool').length")
    check('Hivey Cyber tools', isinstance(tools, int) and tools >= 10, f'{tools} tools in the popup')
    p.shot('hivey-cyber')
    p.goto('chrome://hivey/', settle=3)
    nav = p.eval("document.querySelectorAll('.nav-item').length")
    check('Hivey Studio loads', nav == 6, f'{nav} sections in the navigation')
    p.shot('hivey-studio')
    p.goto('about:blank', settle=0.5)
    p.goto('chrome://hivey/#resources', settle=4)
    gauge = p.eval("document.querySelector('#gauge-ram .gauge-value')?.textContent")
    check('Hivey Studio live usage', bool(gauge) and gauge != '–', f'memory gauge shows {gauge!r}')
    p.shot('hivey-studio-resources')

    # The toolbar button's bubble page: the Resources section alone.
    p.goto('chrome://hivey-resources.top-chrome/', settle=4)
    bubble = p.eval("({bubble: document.body.classList.contains('in-bubble'),"
                    " nav: document.querySelectorAll('.nav-item').length,"
                    " gauge: document.querySelector('#gauge-ram .gauge-value')?.textContent})")
    check('Resources bubble page', isinstance(bubble, dict) and bubble['bubble'] and
          bubble['gauge'] not in (None, '–'), f'{bubble}')
    p.shot('hivey-resources-bubble')

    # Security defaults, from the content settings Hivey Studio reads.
    p.goto('chrome://hivey/#privacy', settle=2)
    st = p.eval(STUDIO_STATE)
    security = st.get('security') if isinstance(st, dict) else st
    check('Device APIs blocked (USB, serial, HID, Bluetooth)',
          isinstance(security, dict) and security.get('devicesBlocked') is True, f'security state: {security}')
    check('Vertical tabs do not expand on hover by default',
          isinstance(st, dict) and st['prefs'].get('vertical_tabs.expand_on_hover') is False,
          f"vertical_tabs.expand_on_hover = {isinstance(st, dict) and st['prefs'].get('vertical_tabs.expand_on_hover')}")

    # Color engine: a custom toolbar color reaches the browser's color
    # provider (Hivey Studio reads its palette from there).
    p.eval("chrome.send('setColor', ['toolbar', '#123456'])")
    time.sleep(1.5)
    toolbar = p.eval(STUDIO_STATE + ".then(s => s.colors.palette.toolbar)")
    p.eval("chrome.send('setColor', ['toolbar', ''])")
    time.sleep(1)
    restored = p.eval(STUDIO_STATE + ".then(s => s.colors.palette.toolbar)")
    check('Custom toolbar color', str(toolbar).lower() == '#123456' and str(restored).lower() != '#123456',
          f'toolbar color {toolbar} set, {restored} after reset')

    # Live refresh: a setting changed elsewhere (here, from another tab)
    # shows up at once in an open Hivey Studio.
    p.goto('chrome://hivey/#tabs', settle=2)
    switches = "document.querySelectorAll('.switch-input').length"
    before = p.eval(switches)
    other = Page()
    other.goto('chrome://hivey/', settle=2)
    other.eval("chrome.send('setPref', ['vertical_tabs.enabled', true])")
    time.sleep(2)
    after = p.eval(switches)
    vertical = p.eval(STUDIO_STATE + ".then(s => s.prefs['vertical_tabs.enabled'])")
    p.shot('hivey-studio-vertical-tabs')
    other.eval("chrome.send('setPref', ['vertical_tabs.enabled', false])")
    time.sleep(1)
    other.close()
    check('Hivey Studio refreshes live', vertical is True and isinstance(before, int) and after == before + 1,
          f'vertical tabs on from another tab: {before} -> {after} switches (hover option shown)')

    # Hivey Studio, end to end: a preset changes the browser color (handler
    # and ThemeService), and the network limiter slows a download down.
    p.goto('about:blank', settle=0.5)
    p.goto('chrome://hivey/#appearance', settle=3)
    before = p.eval("getComputedStyle(document.documentElement).getPropertyValue('--user').trim()")
    p.eval("document.querySelectorAll('.swatch')[1].click()")
    time.sleep(2)
    p.goto('about:blank', settle=0.5)
    p.goto('chrome://hivey/#appearance', settle=3)
    after = p.eval("getComputedStyle(document.documentElement).getPropertyValue('--user').trim()")
    check('Hivey Studio color preset', after.lower() == '#6366f1' and before != after,
          f'browser color {before} -> {after} (Aura accent)')
    p.shot('hivey-studio-aura')
    p.eval("chrome.send('applyPreset', ['aura'])")  # back to the default theme
    time.sleep(1)

    def timed_download():
        return p.eval(f"""(async () => {{ const t = performance.now();
          const r = await fetch('http://127.0.0.1:{PORT}/blob?' + Math.random(), {{cache: 'no-store'}});
          await r.arrayBuffer(); return (performance.now() - t) / 1000; }})()""")
    p.eval("chrome.send('setPref', ['hivey.network_limit_kbps', 1000])")
    time.sleep(2)
    p.goto(f'http://localhost:{PORT}/page', settle=1)
    slow = timed_download()
    p.goto('chrome://hivey/', settle=2)
    p.eval("chrome.send('setPref', ['hivey.network_limit_kbps', 0])")
    time.sleep(2)
    p.goto(f'http://localhost:{PORT}/page', settle=1)
    fast = timed_download()
    # CPU limiter (Windows): a busy loop does much less work under a 10 % cap.
    if p.eval("navigator.userAgentData.platform") == 'Windows':
        busy = "(() => { const t = performance.now(); let n = 0; while (performance.now() - t < 3000) n++; return n; })()"
        p.goto(f'http://localhost:{PORT}/page', settle=1)
        free_run = p.eval(busy)
        p.goto('chrome://hivey/', settle=2)
        p.eval("chrome.send('setPref', ['hivey.cpu_limit_percent', 10])")
        time.sleep(2)
        p.goto(f'http://localhost:{PORT}/page?capped', settle=2)
        capped = p.eval(busy)
        p.goto('chrome://hivey/', settle=2)
        p.eval("chrome.send('setPref', ['hivey.cpu_limit_percent', 0])")
        time.sleep(1)
        ratio = capped / free_run if isinstance(capped, int) and isinstance(free_run, int) and free_run else None
        check('CPU limiter (10 % cap)', ratio is not None and ratio < 0.7,
              f'busy loop: {free_run} iterations free, {capped} capped (ratio {ratio and round(ratio, 2)})')

    check('Network limiter', isinstance(slow, (int, float)) and isinstance(fast, (int, float)) and
          slow > 2.5 and fast < 1, f'400 KB in {slow:.1f} s at 1 Mb/s, {fast:.2f} s without limit'
          if isinstance(slow, (int, float)) and isinstance(fast, (int, float)) else f'{slow!r} {fast!r}')

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

    # 4. Content blocker, seen from the network: ad and tracker requests are
    # blocked or replaced by a harmless surrogate; a normal request goes through.
    def add_script(url):
        return f"""(() => {{ const s = document.createElement('script'); s.src = '{url}?t=' + Date.now();
          document.head.appendChild(s); return true; }})()"""
    ad = p.request_outcome(add_script('https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'),
                           'googlesyndication.com')
    tracker = p.request_outcome(add_script('https://www.google-analytics.com/analytics.js'), 'google-analytics.com')
    pixel = p.request_outcome("fetch('https://www.facebook.com/tr?id=1&ev=PageView&t=' + Date.now(),"
                              " {mode: 'no-cors'}).catch(() => 0)", 'facebook.com/tr')
    control = p.request_outcome("fetch('https://httpbin.org/get?t=' + Date.now()).catch(() => 0)", 'httpbin.org/get')
    check('Ad script stopped (googlesyndication)', ad.startswith(('blocked', 'neutralized')), f'ad script {ad}')
    check('Tracker stopped (google-analytics)', tracker.startswith(('blocked', 'neutralized')), f'tracker {tracker}')
    check('Tracking pixel stopped (facebook.com/tr)', pixel.startswith(('blocked', 'neutralized')), f'pixel {pixel}')
    check('Normal request allowed', control == 'loaded', f'httpbin.org {control}')

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
