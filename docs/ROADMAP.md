# Roadmap

Windows x64 and Linux x64. Each item is checked on a real build before it is
ticked: Linux on the build host, Windows on a GitHub Actions runner.

## Phase 0: Foundations

- [x] Reproducible cross-build from Linux (no Windows machine needed)
- [x] ungoogled-chromium base, pinned and verified
- [x] Branding: name, install/user-data paths, ProgIDs, translated strings
- [x] Build that cannot starve a shared host (priority, memory cap, LTO threads)
- [x] Windows installer, tested on Windows 11 (154, 2026-10-06)
- [x] Logo and icons, own COM CLSIDs
- [x] Chromium 156 (patch stack checked without a build: `scripts/patchcheck.py`, CI on every change)
- [x] Linux build (same tree, portable `.tar.xz`)

## Phase 1: Privacy and security

- [x] Built-in content blocker: uBlock Origin Lite (ads, trackers, malware, cosmetic filtering, scriptlets)
- [x] Cookie banners and tracking parameters removed (uBOL rulesets on by default)
- [x] Blocked-requests counter in the toolbar
- [x] Fingerprinting deception: canvas, measureText, ClientRects, audio
- [x] GPU vendor/model hidden from WebGL; processor count capped at 8
- [x] Font fingerprinting protection (standard fonts only)
- [x] Cross-origin referrers cut to the origin
- [x] No Topics, Attribution Reporting, fenced frames
- [x] Global Privacy Control, HTTPS-only (strict), encrypted DNS (Quad9)
- [x] Hardened defaults from ungoogled-chromium: third-party cookies blocked, no hyperlink auditing, no prefetch, WebRTC without non-proxied UDP
- [x] DuckDuckGo as default search engine (local new tab page)
- [x] Zero requests at startup, checked on a fresh profile (`tests/startup_requests.py`)
- [ ] Per-site "forget when closed"

## Phase 2: Resource control (GX-style)

- [x] Memory Saver on by default
- [x] RAM limiter
- [x] CPU limiter (Windows)
- [x] Network limiter
- [x] Live usage gauges and hot tabs (Hivey Studio > Resources)
- [ ] CPU limiter on Linux (cgroups)

## Phase 3: Look and feel

- [x] Hivey Studio (`chrome://hivey`): colors, layout, tabs, resources, privacy, updates
- [x] Any color for the whole browser, palette styles, light/dark, grayscale
- [x] Vertical tabs, side panel position, toolbar buttons, compact mode
- [x] Custom new tab page
- [ ] Built-in animations, with a reduced-motion mode
- [ ] Theme import/export

## Phase 4: Hivey AI sidebar

- [ ] Native side panel, like Leo in Brave
- [ ] Bring your own key, or local models
- [ ] Off by default; nothing sent until the user turns it on

## Phase 5: Distribution

- [x] Automatic updates from signed releases (Windows install, Linux notice)
- [x] Automatic Chromium updates: build, test, release (`scripts/autoupdate.py`)
- [ ] Code-signed Windows installer (needs a certificate)
- [ ] Download page
- [ ] Linux packages (AppImage, .deb)
