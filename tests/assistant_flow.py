#!/usr/bin/env python3
"""The assistant from end to end, in the real browser, as a user: a question typed
in the new tab, the panel opening without its rail, the model downloaded on a
click, an answer written by the local engine with web sources, a follow-up that
keeps the topic, music asked of the agent on a new tab, and the pause during a
game. Fails if the browser does not really answer.

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
AI_ID = 'lkcmbmbhbkaihiiioilbfoamihehnhce'
SIDEBAR = f'chrome-extension://{AI_ID}/src/sidebar/sidebar.html'
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
        self.ws = websocket.create_connection(info['webSocketDebuggerUrl'], suppress_origin=True, timeout=60)
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


def new_tab(url):
    request = urllib.request.Request(f'{BASE}/json/new?{url}', method='PUT')
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


IDLE = "document.getElementById('stop').classList.contains('hidden')"
LAST = ("(() => { const m = [...document.querySelectorAll('#messages .msg.assistant')].pop();"
        " return m ? m.innerText : ''; })()")
COUNT = "document.querySelectorAll('#messages .msg.assistant').length"


def wait_answer(panel, before, timeout):
    wait_for('the answer', lambda: panel.js(f"{COUNT} > {before} && {IDLE}"), timeout, 2)
    return panel.js(LAST) or ''


def send(panel, text):
    before = panel.js(COUNT)
    panel.js(f"(() => {{ const i = document.getElementById('input'); i.value = {json.dumps(text)};"
             "i.dispatchEvent(new Event('input', {bubbles: true}));"
             "i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true})); })()")
    return before


def ask_from_new_tab(chip, text):
    tab = Target(new_tab('chrome://newtab/'))
    wait_for('the field', lambda: tab.js("!!document.getElementById('q')"), 30)
    tab.js(f"document.querySelector('.chip[data-mode={chip}]').click();"
           f"document.getElementById('q').value = {json.dumps(text)};"
           "document.getElementById('form').requestSubmit()")
    return tab


def diagnose(panel, tab):
    """What to know when a question from a new tab did not arrive."""
    print('      panels:', [t['url'][-40:] for t in targets() if SIDEBAR in t.get('url', '')], flush=True)
    print('      panel url:', panel.js('location.href'), flush=True)
    print('      storage:', panel.js("chrome.storage.local.get(['pendingAction', 'hiveyAi', 'hiveyAiBusy', 'hiveyAiAgent'])"
                                     ".then(r => { if (r.hiveyAi) r.hiveyAi.key = ''; return JSON.stringify(r); })"), flush=True)
    print('      messages:', (panel.js("document.getElementById('messages').innerText") or '')[-300:].replace('\n', ' '), flush=True)
    print('      new tab:', tab.js("JSON.stringify({url: location.href, value: document.getElementById('q')?.value, "
                                   "chip: document.querySelector('.chip[aria-pressed=true], .chip.active')?.dataset.mode})"), flush=True)


def run(args):
    wait_for('the browser', lambda: _up(), 60)

    # The new tab asks; the panel opens, without its rail.
    tab = ask_from_new_tab('ask', 'Quelle est la capitale de la France ?')
    panel_info = wait_for('the panel', lambda: find_target(SIDEBAR), 30)
    panel = Target(panel_info)
    wait_for('the panel page', lambda: panel.js("!!document.getElementById('input')"), 30)
    check('The question opens the assistant', 'embed=hivey' in panel_info['url'], panel_info['url'][-40:])
    check('No rail in the panel', panel.js("getComputedStyle(document.getElementById('rail')).display") == 'none', '')
    time.sleep(2)
    panel.shot(args.out / 'assistant-1-opened.png')

    # The model: asked for, never downloaded by itself.
    if not args.model_from:
        wait_for('the card', lambda: panel.js("!!document.querySelector('.engine-card button')"), 30)
        check('The model waits for a click', True, panel.js("document.querySelector('.engine-card').innerText")[:80].replace('\n', ' '))
        panel.js("document.querySelector('.engine-card button').click()")
        start = time.monotonic()
        wait_for('the download', lambda: not panel.js("!!document.querySelector('.engine-card')"), 1500, 2)
        check('Model downloaded and verified', True, f'{time.monotonic() - start:.0f} s')

    # An answer from the local engine, with sources.
    text = wait_answer(panel, 0, 900)
    check('Answer from the local engine', len(text) > 10, text[:200].replace('\n', ' '))
    check('Paris in the answer', 'paris' in text.lower(), '')
    state = panel.js("chrome.storage.local.get('hiveyAi').then(r => r.hiveyAi.state + ' ' + r.hiveyAi.modelName)")
    check('On the local engine', str(state).startswith('running'), str(state))
    keys = panel.js("chrome.storage.local.get('keys').then(r => JSON.stringify(r.keys || {}))")
    secret = panel.js("chrome.storage.local.get('hiveyAi').then(r => r.hiveyAi.key)")
    check('Its key stays out of the keys given to web pages', bool(secret) and secret not in str(keys), '')
    panel.shot(args.out / 'assistant-2-answer.png')

    # A follow-up keeps the topic.
    before = send(panel, 'Et sa population ?')
    text = wait_answer(panel, before, 600)
    check('A follow-up keeps the topic', len(text) > 5 and any(w in text.lower() for w in ('paris', 'habitant', 'million')), text[:200].replace('\n', ' '))

    # A game: nothing is computed, then it resumes.
    settings = Target(new_tab('chrome://hivey-assistant/'))
    wait_for('the test page', lambda: settings.js("!!document.getElementById('feed')"), 20)
    before = send(panel, 'Sans chercher sur le web, écris un long texte sur le fonctionnement d\'un navigateur web.')
    try:
        wait_for('the writing', lambda: panel.js(f"{COUNT} > {before} && ({LAST}).length > 30"), 300, 0.5)
    except TimeoutError:
        panel.shot(args.out / 'assistant-writing-timeout.png')
        print('      before', before, 'count', panel.js(COUNT), 'idle', panel.js(IDLE), flush=True)
        print('      messages:', (panel.js("document.getElementById('messages').innerText") or '')[-400:].replace('\n', ' '), flush=True)
        print('      input:', repr(panel.js("document.getElementById('input').value")), flush=True)
        raise
    settings.js("chrome.send('setGameForTesting', [true])")
    time.sleep(4)
    first = len(panel.js(LAST) or '')
    time.sleep(6)
    second = len(panel.js(LAST) or '')
    check('Game: the answer stops', first == second, f'{first} -> {second} characters in 6 s')
    panel.shot(args.out / 'assistant-3-game.png')
    settings.js("chrome.send('setGameForTesting', [false])")
    wait_for('the resume', lambda: len(panel.js(LAST) or '') > second, 90, 0.5)
    check('Game over: the answer resumes', True, f'{second} -> {len(panel.js(LAST) or "")} characters')
    panel.js("document.getElementById('stop').click()")
    wait_for('the stop', lambda: panel.js(IDLE), 30)

    # The agent on a new tab: music.
    tabs_before = len([t for t in targets() if t['type'] == 'page'])
    music = ask_from_new_tab('agent', 'Lance-moi une musique')
    before = panel.js(COUNT)
    end = time.monotonic() + 600
    playing = None
    while time.monotonic() < end and not playing:
        time.sleep(5)
        for info in targets():
            if 'youtube' in info.get('url', '') and info['type'] == 'page':
                playing = info
    check('Agent: goes to the music, from the new tab', bool(playing), playing['url'][:70] if playing else 'no player page')
    if not playing:
        diagnose(panel, music)
    print('      panel:', (panel.js(LAST) or '')[:200].replace('\n', ' '), flush=True)
    print(f"      tabs: {tabs_before} -> {len([t for t in targets() if t['type'] == 'page'])}")
    # What was asked: a video that plays, not a list of results.
    def watch_page():
        for info in targets():
            if '/watch' in info.get('url', '') and info['type'] == 'page':
                return info
        return None
    watch = None
    try:
        watch = wait_for('a video page', watch_page, 600, 3)
    except TimeoutError:
        pass
    check('Agent: opens a video', bool(watch), watch['url'][:70] if watch else 'still on the results')
    if watch:
        player = Target(watch)
        video = ("(() => { const v = document.querySelector('video');"
                 " return v ? {t: v.currentTime, paused: v.paused, muted: v.muted} : null; })()")
        time.sleep(8)
        first_state = player.js(video)
        time.sleep(8)
        second_state = player.js(video)
        print(f'      video: {first_state} -> {second_state}', flush=True)
        moving = bool(first_state and second_state and second_state['t'] > first_state['t'] and not second_state['muted'])
        check('Agent: the music plays, with sound', moving or args.no_play_check, f'{first_state} -> {second_state}')
    print('      panel at the end:', (panel.js(LAST) or '')[:200].replace('\n', ' '), flush=True)
    panel.shot(args.out / 'assistant-4-agent.png')

    # The agent's access to sites ends with its work.
    def sites_closed():
        return panel.js("chrome.permissions.contains({origins: ['<all_urls>']}).then(r => !r)")
    wait_for('the sites taken back', sites_closed, 20)
    check('Agent: the sites are taken back after it', True, '')

    # A question for the web: real results, read through the browser, with sources.
    before = send(panel, 'Quel est le meilleur healer sur Overwatch ?')
    text = wait_answer(panel, before, 900)
    links = panel.js("[...document.querySelectorAll('#messages .msg.assistant')].pop().querySelectorAll('a[href^=\"http\"]').length")
    check('Web: an answer with its sources', len(text) > 20 and links > 0, f'{links} links: {text[:160]}'.replace('\n', ' '))
    panel.shot(args.out / 'assistant-5-web.png')

    # Right after the answer, the engine leaves the PC's memory.
    start = time.monotonic()
    state = "chrome.storage.local.get('hiveyAi').then(r => r.hiveyAi.state)"
    wait_for('the engine to stop', lambda: panel.js(state) != 'running', 90)
    check('Engine unloaded after the answer', True, f'{time.monotonic() - start:.0f} s, state {panel.js(state)}')

    # It comes back for the next question, and the conversation is still there.
    before = send(panel, 'Et en compétition ?')
    text = wait_answer(panel, before, 900)
    check('After the unload: the follow-up keeps the topic', any(w in text.lower() for w in ('overwatch', 'healer', 'soin', 'support', 'héros', 'hero')), text[:200].replace('\n', ' '))

    # A real agent turn, through the model and its tools.
    opener = ask_from_new_tab('agent', 'Ouvre le site example.com')
    def example_page():
        return next((t for t in targets() if 'example.com' in t.get('url', '') and t['type'] == 'page'), None)
    opened = None
    try:
        opened = wait_for('the site', example_page, 600, 3)
    except TimeoutError:
        pass
    check('Agent: the model acts on the browser', bool(opened), opened['url'][:60] if opened else (panel.js(LAST) or '')[:200])
    if not opened:
        diagnose(panel, opener)
    wait_for('the end of the turn', lambda: panel.js(IDLE), 600, 2)
    wait_for('the sites taken back', sites_closed, 20)
    check('Agent: the sites are taken back after a real turn', True, '')


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('browser')
    parser.add_argument('out', type=Path)
    parser.add_argument('--model-from', type=Path)
    # For a machine where the site itself refuses to play (this project's server).
    parser.add_argument('--no-play-check', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix='hivey-ai-'))
    if args.model_from:
        (profile / 'HiveyAI').mkdir()
        shutil.copy2(args.model_from, profile / 'HiveyAI' / args.model_from.name)
    command = [args.browser, f'--user-data-dir={profile}', f'--remote-debugging-port={PORT}', '--no-first-run',
               '--password-store=basic', '--hivey-ai-test-game', '--window-size=1440,900']
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


def _up():
    try:
        return bool(targets())
    except OSError:
        return False


if __name__ == '__main__':
    main()
