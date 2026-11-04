#!/usr/bin/env python3
"""The local AI from end to end, as a user: a question typed in the new tab,
the panel opening, the model downloaded, an answer actually written by the
engine, with web sources, from the page, without a source, and the pause during
a game. Fails if the browser does not really answer.

    assistant_flow.py <browser> <output dir> [--model-from <file>]

--model-from copies a model already there instead of downloading it (local runs;
CI downloads it, as a user does).
"""
import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

import websocket

PORT = 9377
BASE = f'http://127.0.0.1:{PORT}'
failures = []


def check(name, ok, detail=''):
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)
    if not ok:
        failures.append(name)


def targets():
    with urllib.request.urlopen(f'{BASE}/json/list', timeout=5) as r:
        return json.load(r)


class Target:
    def __init__(self, info):
        self.ws = websocket.create_connection(info['webSocketDebuggerUrl'], suppress_origin=True, timeout=30)
        self.next_id = 0

    def call(self, method, **params):
        self.next_id += 1
        self.ws.send(json.dumps({'id': self.next_id, 'method': method, 'params': params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get('id') == self.next_id:
                return message.get('result', {})

    def js(self, expression):
        result = self.call('Runtime.evaluate', expression=expression, returnByValue=True, awaitPromise=True)
        return result.get('result', {}).get('value')

    def shot(self, path):
        data = self.call('Page.captureScreenshot', format='png').get('data')
        if data:
            Path(path).write_bytes(base64.b64decode(data))


def wait_for(what, predicate, timeout, every=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(every)
    raise TimeoutError(what)


def find_target(fragment):
    for info in targets():
        if fragment in info.get('url', '') and 'webSocketDebuggerUrl' in info:
            return info
    return None


def ask_in_panel(panel, source, question):
    panel.js(f"document.querySelector('.chip[data-source={source}]').click()")
    before = panel.js("document.querySelectorAll('.answer').length")
    plans = panel.js("document.querySelectorAll('.plan').length")
    panel.js(f"document.getElementById('q').value = {json.dumps(question)};"
             "document.getElementById('composer').requestSubmit()")
    # This question's own plan is there before waiting for its end.
    wait_for('the plan', lambda: panel.js(f"document.querySelectorAll('.plan').length > {plans}"), 10, 0.2)
    return wait_answer(panel, before)


def wait_answer(panel, before, timeout=420):
    # The answer is finished when the ledger after it is there (or an error).
    wait_for('the answer', lambda: panel.js(
        "!document.body.classList.contains('busy') && ("
        f"document.querySelectorAll('.answer').length > {before}"
        " || [...document.querySelectorAll('.plan')].pop()?.querySelector('li.failed') !== null)"), timeout)
    return panel.js("(() => { const a = [...document.querySelectorAll('.answer')].pop();"
                    " return a ? a.textContent : ''; })()")


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('browser')
    parser.add_argument('out', type=Path)
    parser.add_argument('--model-from', type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix='hivey-ai-'))
    if args.model_from:
        (profile / 'HiveyAI').mkdir()
        shutil.copy2(args.model_from, profile / 'HiveyAI' / 'model.gguf')
    command = [args.browser, f'--user-data-dir={profile}', f'--remote-debugging-port={PORT}', '--no-first-run',
               '--password-store=basic', '--hivey-ai-test-game', '--window-size=1440,900', 'chrome://newtab/']
    if sys.platform != 'win32':
        command.insert(1, '--no-sandbox')
    browser = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        run(args)
    except Exception as error:  # A failed step ends the run with what it knows.
        traceback.print_exc()
        check('the flow went to the end', False, repr(error))
    finally:
        browser.kill()
        browser.wait()
        shutil.rmtree(profile, ignore_errors=True)
    print(f"\n{'all passed' if not failures else f'{len(failures)} failed: {failures}'}")
    sys.exit(1 if failures else 0)


def run(args):
    wait_for('the browser', lambda: _up(), 60)
    # A new profile opens Hivey Settings first.
    request = urllib.request.Request(f'{BASE}/json/new?chrome://newtab/', method='PUT')
    with urllib.request.urlopen(request, timeout=10) as response:
        tab = Target(json.load(response))
    wait_for('the field', lambda: tab.js("!!document.getElementById('q')"), 30)
    chips = tab.js("[...document.querySelectorAll('.chip')].map(c => c.dataset.mode).join()")
    check('New tab: only what works', chips == 'web,ask', chips)

    # The question goes to the panel.
    tab.js("document.querySelector('.chip[data-mode=ask]').click();"
           "document.getElementById('q').value = 'Quelle est la capitale de la France ?';"
           "document.getElementById('form').requestSubmit()")
    panel_info = wait_for('the panel', lambda: find_target('hivey-assistant'), 30)
    panel = Target(panel_info)
    wait_for('the panel page', lambda: panel.js("!!document.getElementById('feed')"), 30)
    check('The question opens the assistant, not Hivey Tools', True, panel_info['url'])
    time.sleep(1)
    panel.shot(args.out / 'assistant-1-opened.png')

    # The model: asked for, never downloaded by itself.
    state = panel.js("document.getElementById('download') ? 'card' : 'none'")
    if not args.model_from:
        check('The model is not downloaded without asking', state == 'card', state)
        panel.js("document.getElementById('download').click()")
        start = time.monotonic()
        wait_for('the download', lambda: not panel.js("!!document.querySelector('.bar') || !!document.getElementById('download')"), 1500, 2)
        check('Model downloaded and verified', True, f'{time.monotonic() - start:.0f} s')

    # The first question, from the new tab, comes with web sources.
    text = wait_answer(panel, 0, 900)
    check('Answer written by the local engine, with the web', len(text) > 10, text[:160])
    sources = panel.js("document.querySelectorAll('.src').length")
    citations = panel.js("document.querySelectorAll('.cite').length")
    print(f'      sources read: {sources}, citations: {citations}')
    check('Paris in the answer', 'paris' in text.lower(), text[:100])
    status = panel.js("document.getElementById('status').textContent")
    check('Status line tells the truth', 'Machine' in status and 'Engine on' in status or 'Moteur actif' in status, status)
    panel.shot(args.out / 'assistant-2-web.png')

    # Without a source.
    text = ask_in_panel(panel, 'none', 'Réponds par un seul mot : quelle couleur a le ciel par beau temps ?')
    check('Answer without a source', len(text) > 1, text[:100])

    # The page the user is on.
    tab.call('Page.navigate', url='data:text/html,<title>x</title>')  # Not a web page.
    time.sleep(1)
    panel.js("document.querySelector('.chip[data-source=page]').click();"
             "document.getElementById('q').value = 'Résume cette page';"
             "document.getElementById('composer').requestSubmit()")
    wait_for('the refusal', lambda: panel.js("[...document.querySelectorAll('.plan')].pop().querySelector('li.failed') !== null"
                                             " && !document.body.classList.contains('busy')"), 30, 0.3)
    check('This page: refuses what is not a web page', True, '')
    tab.call('Page.navigate', url='https://example.com/')
    time.sleep(4)
    text = ask_in_panel(panel, 'page', 'De quoi parle cette page ? Réponds en une phrase.')
    check('This page: answers from it', len(text) > 10 and not panel.js(
        "[...document.querySelectorAll('.plan')].pop().querySelector('li.failed') !== null"), text[:140])

    # A game: the engine computes nothing, then resumes.
    panel.js("document.querySelector('.chip[data-source=none]').click();"
             "document.getElementById('q').value = 'Écris un long texte sur l\\'histoire du navigateur web.';"
             "document.getElementById('composer').requestSubmit()")
    before = panel.js("document.querySelectorAll('.answer').length")
    wait_for('the writing', lambda: panel.js("(() => { const a = [...document.querySelectorAll('.answer')].pop();"
                                             " return a && a.textContent.length > 30; })()"), 120, 0.5)
    panel.js("chrome.send('setGameForTesting', [true])")
    time.sleep(3)
    length = lambda: panel.js("[...document.querySelectorAll('.answer')].pop().textContent.length")
    first = length()
    time.sleep(6)
    second = length()
    check('Game: the answer stops', first == second, f'{first} -> {second} characters in 6 s')
    check('Game: said in the panel', 'game' in panel.js("document.getElementById('status').textContent") or
          'jeu' in panel.js("document.getElementById('status').textContent"), '')
    panel.shot(args.out / 'assistant-3-game.png')
    panel.js("chrome.send('setGameForTesting', [false])")
    wait_for('the resume', lambda: length() > second, 60, 0.5)
    check('Game over: the answer resumes', True, f'{second} -> {length()} characters')
    panel.js("document.getElementById('composer').requestSubmit()")  # Stop it.
    wait_for('the stop', lambda: panel.js("!document.body.classList.contains('busy')"), 30)
    panel.shot(args.out / 'assistant-4-end.png')


def _up():
    try:
        return bool(targets())
    except OSError:
        return False


if __name__ == '__main__':
    main()
