# User guide

## Install

- **Windows x64**: run `hivey-browser-<version>-windows-x64-installer.exe`
  from the [latest release](https://github.com/FlorianMartins/hivey-browser/releases/latest).
  It installs for your user only (no administrator rights) and keeps its data
  in `%LOCALAPPDATA%\Hivey\Browser\User Data`, separate from Chrome or
  Chromium.
- **Linux x64**: extract `hivey-browser-<version>-linux-x64.tar.xz` anywhere
  and run `hivey-browser`. Data goes to `~/.config/hivey-browser` (or the
  folder chosen by the build's branding). `hivey-browser.desktop` and
  `hivey-browser.png` are there for your menu.

The first window opens **Hivey Studio**, where everything below can be
changed. Open it later from the menu (⋮ > *Hivey Studio*) or at
`chrome://hivey`.

## Updates

Hivey Browser keeps itself up to date. It checks for a new version 10
minutes after it starts and then twice a day; on Windows it installs it in
the background and the menu shows *Relaunch to update*. On Linux, Hivey
Studio > About shows the new version with a download link. Updates are
signed: the browser refuses anything else. *Hivey Studio > About* shows the
status, checks on demand, and turns automatic updates off.

## Privacy, out of the box

- **Hivey Shield** (uBlock Origin Lite, the shield icon in the toolbar)
  blocks ads, trackers, cookie banners, tracking parameters in links and
  malware sites, and hides the empty boxes ads leave. The number on the icon
  counts what it blocked on the page. Click it to relax or tighten filtering
  for a site.
- **Third-party cookies blocked**, **secure connections only** (a warning
  before any plain-HTTP page), **encrypted DNS** through Quad9, **Global
  Privacy Control**, and **DuckDuckGo** for searches.
- **Fingerprinting protection.** Sites cannot recognize your computer from
  how it draws, measures text, plays audio, which fonts it has or which GPU it
  uses. If a site that draws or processes sound misbehaves, turn
  *Anti-fingerprinting* off in Hivey Studio > Privacy and restart.
- **Referrers** sent to other sites only say which site you came from, never
  the page.
- **No Google services, no telemetry, no crash reports**, and no request at
  startup.

## Hivey Studio

| Section | What you can do |
| --- | --- |
| Colors | Pick a preset or **any color**: tabs, toolbar, menus and dialogs follow it. Choose the palette style (tonal, neutral, vibrant, expressive), light/dark/system mode, grayscale, and whether Incognito windows use it. |
| Layout | **Vertical tabs** (expand on hover), **compact mode**, side panel left or right, Home and Forward buttons, bookmarks bar, tab search button, profile button, extensions menu, toolbar buttons, a **custom new tab page**, fonts and default zoom. |
| Tabs & behaviour | Ctrl+Tab in recently-used order, the mouse wheel over the tab strip, keep the window open when closing its last tab, hide tab close buttons, pop-ups as tabs, tab previews, ask before closing. |
| Resources | Live CPU, memory and network gauges; the **hot tabs** (show or close them); the **RAM limiter** (background tabs go to sleep above the limit), the **CPU limiter** (Windows: a hard cap per tab) and the **network limiter** (bandwidth for the whole browser, downloads included). |
| Privacy & security | Hivey Shield status, anti-fingerprinting, secure connections, clear data on exit, secure DNS and cookie settings. |
| About | Version and automatic updates. |

Options marked ↻ apply after a restart; Hivey Studio offers a *Restart*
button when one is pending.

## Memory and performance

- **Memory Saver** is on: tabs you have not used for a while are put to
  sleep and reload when you come back. *Settings > Performance* sets how
  aggressive it is and which sites always stay awake.
- The **RAM limiter** is a soft limit: it checks every 30 seconds and puts
  the least recently used background tabs to sleep until the browser is back
  under the limit. Tabs playing audio or with a form being filled are kept.
  Measured on Windows with a 1 GB limit and 12 news sites open: 1.23 GB, then
  1.01 GB.

## Advanced switches

`chrome://flags` lists every Hivey Browser and ungoogled-chromium option
(search for "Hivey" or "ungoogled"); Hivey Studio shows the useful ones.
