#!/usr/bin/env python3
"""Types addresses in the address bar with real key presses (Windows) and
records where the tab goes: the user's "kamaraderie.fr opens Google" report.

    omnibox_typed.py <browser executable> <output dir> [--port 9334]

For the record, not a pass/fail check: prints each case and keeps a
screenshot of the suggestions before Enter.
"""
import ctypes
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

BROWSER = sys.argv[1]
OUT = Path(sys.argv[2])
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 9334
CASES = [('ctrl+l', 'Kamaraderie.fr'), ('ctrl+t', 'Kamaraderie.fr'), ('ctrl+t', 'kamaraderie.fr'),
         ('ctrl+t', 'wikipedia.org')]

user32 = ctypes.WinDLL('user32', use_last_error=True)
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x2, 0x4
VK = {'ctrl': 0x11, 'l': 0x4C, 't': 0x54, 'enter': 0x0D}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT), ('pad', ctypes.c_byte * 32)]
    _anonymous_ = ('u',)
    _fields_ = [('type', wintypes.DWORD), ('u', _U)]


def send(vk=0, scan=0, flags=0):
    event = INPUT(type=INPUT_KEYBOARD)
    event.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    time.sleep(0.03)


def chord(keys):
    codes = [VK[k] for k in keys.split('+')]
    for code in codes:
        send(code)
    for code in reversed(codes):
        send(code, flags=KEYEVENTF_KEYUP)


def type_text(text):
    for ch in text:
        send(scan=ord(ch), flags=KEYEVENTF_UNICODE)
        send(scan=ord(ch), flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        time.sleep(0.05)


def focus_browser():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, 256)
        if name.value == 'Chrome_WidgetWin_1' and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    for hwnd in found:
        user32.ShowWindow(hwnd, 3)  # maximized
        user32.SetForegroundWindow(hwnd)
    time.sleep(1)


def active_url():
    pages = [t for t in json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/list'))
             if t['type'] == 'page']
    return pages[0]['url'] if pages else ''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.mkdtemp(prefix='hivey-omnibox-'))
    browser = subprocess.Popen([BROWSER, f'--user-data-dir={profile}', f'--remote-debugging-port={PORT}',
                                '--no-first-run', '--start-maximized'])
    try:
        time.sleep(20)
        for i, (keys, text) in enumerate(CASES):
            focus_browser()
            chord(keys)
            time.sleep(3)
            type_text(text)
            time.sleep(2.5)
            ImageGrab.grab().save(OUT / f'omnibox-{i}-{text}.png')
            chord('enter')
            time.sleep(8)
            print(f'{keys} + {text!r} -> {active_url()}')
    finally:
        browser.terminate()
        time.sleep(2)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == '__main__':
    main()
