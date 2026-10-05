# User guide

> Hivey Browser has no public release yet. This guide describes the
> behavior of builds made from this repository.

## First start

Hivey Browser keeps its data in `%LOCALAPPDATA%\Hivey\Browser\User Data`,
separate from Chrome or Chromium. Nothing is sent anywhere at startup.

## Privacy, out of the box

These protections are on without any setup:

- **Third-party cookies blocked.**
- **Secure connections only.** Before loading a page over plain HTTP, the
  browser shows a warning; you can continue or go back. To relax it:
  *Settings > Privacy and security > Security > Always use secure
  connections*.
- **Encrypted DNS.** The sites you visit are looked up through Quad9 over
  an encrypted connection, so your network provider cannot see them. To use
  your system's DNS instead: *Settings > Privacy and security > Security >
  Use secure DNS*.
- **Global Privacy Control.** Every site is told you do not want your data
  sold or shared.
- **Fingerprinting deception.** Small random changes to a few drawing APIs
  stop sites from recognizing your browser across visits. If a site that
  draws in a canvas (a game, an image editor) misbehaves, turn on
  `chrome://flags/#disable-fingerprinting-noise` and restart.
- **GPU hidden.** Sites using WebGL cannot read your graphics card model.
- **No Google services, no telemetry, no crash reports.**

## Colors and look

The browser uses Hivey amber by default. To change it, open a new tab,
click **Customize** (bottom right), then **Appearance**: pick a color, a
color style, light/dark/system mode, or go back to *Default*.

## Advanced switches

`chrome://flags` lists every Hivey Browser and ungoogled-chromium option
(search for "Hivey" or "ungoogled").
