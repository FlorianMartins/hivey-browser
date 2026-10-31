#!/usr/bin/env python3
"""Screenshots of every page of the setup wizard on a real Windows desktop
(how it is drawn there: themes, DPI), pressing Enter from page to page; it
installs, like a user would.

    setup_shots.py <setup wizard .exe> <output dir>

For the record, not a pass/fail check: CI keeps the pictures as artifacts.
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

SETUP = sys.argv[1]
OUT = Path(sys.argv[2])
PAGES = ['1-welcome', '2-license', '3-components', '4-folder', '5-installing', '6-finish']

user32 = ctypes.WinDLL('user32', use_last_error=True)


def wizard_window():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        if 'Hivey' in title.value and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return found[0] if found else None


def grab(hwnd, name):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(OUT / f'{name}.png')


def dump(hwnd):
    """The page's controls (class, ID, size), to tell what draws what."""
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(child, _):
        if user32.IsWindowVisible(child):
            name = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(child, name, 64)
            rect = wintypes.RECT()
            user32.GetWindowRect(child, ctypes.byref(rect))
            print(f'  {name.value} id={user32.GetDlgCtrlID(child)} '
                  f'{rect.right - rect.left}x{rect.bottom - rect.top}')
        return True

    user32.EnumChildWindows(hwnd, each, 0)


def press_enter(hwnd):
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    user32.keybd_event(0x0D, 0, 0, 0)
    user32.keybd_event(0x0D, 0, 2, 0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    subprocess.Popen([SETUP])
    hwnd = None
    for _ in range(60):
        time.sleep(1)
        hwnd = wizard_window()
        if hwnd:
            break
    if not hwnd:
        print('no wizard window')
        return
    time.sleep(3)
    for page in PAGES:
        hwnd = wizard_window() or hwnd
        grab(hwnd, page)
        print('page', page)
        dump(hwnd)
        if page == '6-finish':
            break
        if page == '5-installing':
            time.sleep(60)  # installs
            continue
        press_enter(hwnd)
        time.sleep(4 if page != '4-folder' else 2)


if __name__ == '__main__':
    main()
