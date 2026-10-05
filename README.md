<p align="center"><img src="brand/logo.svg" width="128" alt="Hivey Browser logo"></p>

# Hivey Browser

A modern, deeply customizable, **privacy-first** web browser built on
[ungoogled-chromium](https://github.com/ungoogled-software/ungoogled-chromium).

- **Private by construction.** No Google services, no telemetry, no crash or
  usage reporting, no field trials. Nothing phones home.
- **No clutter.** No crypto wallet, no rewards, no news feed, no sponsored
  tiles, no paid VPN upsell.
- **Yours to shape.** Themes, colors, built-in animations, and per-site
  resource limits (planned, see the [roadmap](docs/ROADMAP.md)).
- **Light on your machine.** RAM and CPU limits, tab sleeping, and a
  memory saver you control (planned).
- **Native AI sidebar.** Hivey AI built in, bring-your-own-key or local
  models, off by default (planned).

> **Status: phase 0 (foundations).** The build pipeline, branding and the
> first Windows x64 build are in progress. There is no downloadable release
> yet.

## Platforms

Windows x64 first. Linux comes next. The Windows build is **cross-compiled
from Linux**, so anyone can reproduce it without a Windows machine.

## Building

```bash
git clone --recurse-submodules https://github.com/FlorianMartins/hivey-browser
cd hivey-browser
XWIN_ACCEPT_LICENSE=1 python3 scripts/hb.py all
```

You need about 120 GB of disk, 32 GB of RAM and several hours for the first
build. See [docs/BUILDING.md](docs/BUILDING.md) for prerequisites, every step,
and how to keep the build from disturbing other services on the same machine.

## How it is made

Hivey Browser is a stack of patches and build scripts, not a fork of the
Chromium repository:

1. the official Chromium source tarball, verified by sha256;
2. ungoogled-chromium's patches, binary pruning and domain substitution;
3. the product patches of ungoogled-chromium-windows;
4. Hivey's own patches (`patches/`) and branding (`brand/brand.json`).

Keeping the patch stack small is what lets us follow Chromium's security
releases quickly. Details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Privacy

See [docs/PRIVACY.md](docs/PRIVACY.md) for what the browser does and does not
send, and how we check it.

## License

The build scripts, patches and assets in this repository are released under
the [MIT license](LICENSE). Chromium and ungoogled-chromium keep their own
licenses (BSD-3-Clause and others); the browser binary includes their notices
at `chrome://credits`.

Hivey Browser is not affiliated with Google or the Chromium project.
