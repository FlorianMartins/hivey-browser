#!/usr/bin/env python3
"""Screenshots of the whole browser window (tab strip, toolbar, Hivey bar,
side panel), not just the page, in a few looks set through Hivey Studio.

    ui_shots.py <browser executable> <output dir> [--port 9333]

Starts the browser maximized on a fresh profile with remote debugging,
drives Hivey Studio's own messages (chrome.send) from a chrome://hivey tab
and grabs the screen with Pillow (ImageGrab: Windows, or X11 with $DISPLAY).
For the record, not a pass/fail check: CI keeps the pictures as artifacts.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client
from PIL import ImageGrab

BROWSER = sys.argv[1]
OUT = Path(sys.argv[2])
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 9333
BASE = f'http://127.0.0.1:{PORT}'


def targets():
    return json.load(urllib.request.urlopen(f'{BASE}/json/list'))


def new_tab(url):
    req = urllib.request.Request(f'{BASE}/json/new?{url}', method='PUT')
    return json.load(urllib.request.urlopen(req))


def evaluate(target, expression):
    ws = websocket.create_connection(target['webSocketDebuggerUrl'], suppress_origin=True, timeout=30)
    try:
        ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                            'params': {'expression': expression, 'awaitPromise': True, 'returnByValue': True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == 1:
                return msg.get('result', {}).get('result', {}).get('value')
    finally:
        ws.close()


def studio(*messages):
    """chrome.send(name, args) calls from the Hivey Studio tab."""
    tab = next((t for t in targets() if t['type'] == 'page' and t['url'].startswith('chrome://hivey/')), None)
    if not tab:
        tab = new_tab('chrome://hivey/')
        time.sleep(3)
    for name, args in messages:
        evaluate(tab, f'chrome.send({json.dumps(name)}, {json.dumps(args)})')
    time.sleep(2.5)


def activate(url_prefix):
    tab = next(t for t in targets() if t['type'] == 'page' and t['url'].startswith(url_prefix))
    urllib.request.urlopen(f'{BASE}/json/activate/{tab["id"]}')
    time.sleep(1.5)


def shot(name):
    OUT.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab().save(OUT / f'{name}.png')
    print('shot', name, flush=True)


profile = Path(tempfile.mkdtemp(prefix='hivey-ui-'))
args = [BROWSER, f'--user-data-dir={profile}', f'--remote-debugging-port={PORT}', '--no-first-run',
        '--start-maximized', '--password-store=basic', 'chrome://hivey/']
if sys.platform.startswith('linux'):
    args[1:1] = ['--no-sandbox', '--test-type']  # CI and test hosts run as root
browser = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            if any(t['url'].startswith('chrome://hivey/') for t in targets()):
                break
        except OSError:
            pass
        time.sleep(1)
    time.sleep(6)
    new_tab('https://example.com/')
    time.sleep(4)
    shot('1-default-aura')
    studio(('setPref', ['vertical_tabs.enabled', True]))
    shot('2-vertical-tabs')
    studio(('setPref', ['hivey.vertical_tabs.right', True]))
    shot('3-vertical-tabs-right')
    studio(('setPref', ['hivey.vertical_tabs.right', False]), ('applyPreset', ['daylight']))
    shot('4-daylight-vertical')
    studio(('applyPreset', ['midnight']), ('setPref', ['vertical_tabs.enabled', False]))
    shot('5-midnight')
    studio(('applyPreset', ['material', '#10b981']))
    activate('chrome://hivey/')
    shot('6-material-studio')
    studio(('applyPreset', ['aura']))
    activate('https://example.com/')
    shot('7-aura-example')
finally:
    browser.terminate()
    try:
        browser.wait(timeout=20)
    except subprocess.TimeoutExpired:
        browser.kill()
    shutil.rmtree(profile, ignore_errors=True)
