# Building Hivey Browser

This guide builds Windows x64 binaries (`chrome.exe` and the
`mini_installer.exe` installer) and Linux x64 binaries **on a Linux host**,
from one patched source tree. No Windows machine or Visual Studio
installation is needed.

## Prerequisites

| What | Why |
| --- | --- |
| Linux x86_64 (tested on Ubuntu 24.04) | build host |
| ~150 GB free disk, 32 GB RAM | source (11 GB) + Windows and Linux build output |
| `python3` ≥ 3.12, `git`, `curl`, `xz` | scripts and downloads |
| `msitools` (`msiextract`, `msiinfo`) | unpack two Windows SDK MSIs |
| `7zip` (or `p7zip-full`) | pack the installer archive |
| `openssl` | sign the bundled extension and the update manifest |
| `xvfb`, Python `websocket-client` (optional) | run the tests on the Linux build |
| Python `cairosvg`, `Pillow` | render the icons |
| [`xwin`](https://github.com/Jake-Shadle/xwin) ≥ 0.10 (release binary, or `cargo install --locked xwin` with a recent Rust) | MSVC CRT + Windows SDK |
| `libfuse2` (Ubuntu: `libfuse2t64`) | case-insensitive mount of the Windows toolchain (ciopfs) |
| `systemd-run` (optional) | memory-capped build |

Accepting the Microsoft license is required for the MSVC/SDK download: set
`XWIN_ACCEPT_LICENSE=1` (the script passes `--accept-license` to xwin).

## One command

```bash
python3 scripts/hb.py all                                   # Windows (HB_TARGET=win, the default)
HB_TARGET=linux python3 scripts/hb.py configure build package  # Linux, same tree
```

`all` runs every step below in order and skips the ones already done
(stamps live in `$HB_BUILD_DIR/.hb-state.json`). `hb.py status` shows
progress. Any single step can be re-run with `hb.py <step> --force`.
`configure`, `build` and `package` are done once per target: Windows builds
in `out/Default`, Linux in `out/Linux`.

## Steps

| Step | What it does |
| --- | --- |
| `fetch` | Downloads the Chromium "lite" source tarball pinned by ungoogled-chromium and checks its sha256. |
| `unpack` | Extracts it into `$HB_BUILD_DIR/src`. |
| `prune` | Deletes prebuilt binaries listed by ungoogled-chromium, except the precompiled MIDL/MC outputs in `win_build_output/` (type libraries and message tables generated from the tree's `.idl`/`.mc` files): Linux has no `midl.exe`/`mc.exe`, so a cross-build needs them. |
| `toolchain` | Fetches **build-only** tools (never shipped): Chromium's pinned clang + Windows runtime, Rust, the Linux sysroot, `rc`, Node, ninja, gn (built from source), the Windows PGO profile, Windows-only sources missing from the lite tarball, and the MSVC CRT + Windows SDK. Must run before `domsub`. |
| `patch` | Applies ungoogled-chromium's patches, the product patches of ungoogled-chromium-windows, then `patches/series`. |
| `brand` | Applies `brand/brand.json` (see below) and writes the version with the Hivey revision (`HIVEY_REVISION`, see [RELEASES.md](RELEASES.md)). |
| `bundle` | Downloads uBlock Origin Lite (`extensions/bundled.json`, sha256-pinned), turns on the extra rulesets listed there, packs it as a signed `.crx`, and generates the headers with its extension ID and with the public key of the update signature. |
| `domsub` | ungoogled-chromium's domain substitution. |
| `configure` | Writes `out/<target>/args.gn` (ungoogled flags, then `flags.hivey.gn`, then `flags.hivey.<target>.gn`) and runs `gn gen`. |
| `build` | Copies the bundled `.crx` next to the browser, then `ninja chrome mini_installer` (Windows) or `ninja chrome` (Linux). |
| `package` | `$HB_BUILD_DIR/dist`: the Windows installer, or a portable Linux `.tar.xz` (browser, launcher, `.desktop` entry, icon); `SHA256SUMS`. |

The `bundle` step creates two private keys the first time (see
[RELEASES.md](RELEASES.md#keys)); keep them, they decide the bundled
extension's ID and which updates installed browsers accept.

## Checking patches without a build

```bash
python3 scripts/patchcheck.py $HB_BUILD_DIR/download_cache/chromium-<version>-lite.tar.xz /tmp/tree
```

applies the whole stack to the files it touches, extracted from the source
tarball, in a few minutes. Hivey patches must apply without fuzz.
`--refresh` rewrites the Hivey patches that only moved. CI runs it on every
change to the patches or submodules. `/tmp/tree` then holds the files as the
build tree has them before branding: copy them to write a new patch with
`scripts/mkpatch.py`.

## Tests

```bash
xvfb-run -a python3 tests/startup_requests.py out/Linux/chrome      # no request at startup
python3 tests/cdp_checks.py http://127.0.0.1:9222 --shots shots/      # privacy checks
```

See [tests/README.md](../tests/README.md).

## Where every Windows piece comes from

Chromium normally gets its Windows toolchain from a zip packaged on a
Windows machine with Visual Studio. We assemble the same layout from
Microsoft's public sources instead, verifying every file:

| Piece | Source | Verified by |
| --- | --- | --- |
| MSVC CRT 14.51, Windows SDK 10.0.28000 headers/libs | VS 2026 manifest, via xwin | sha256 in the manifest |
| VC++ redistributable DLLs | same manifest, `Microsoft.VC.<ver>.CRT.Redist.*` | sha256 in the manifest |
| `d3dcompiler_47.dll`, DXC DLLs | same manifest, SDK MSI "Windows Store Apps Tools" | sha256 in the manifest |
| `dbghelp.dll`, `dbgcore.dll` | NuGet `Microsoft.Debugging.Platform.DbgEng` | sha256 pinned in `hb.py` (checked against the NuGet catalog's SHA512) |
| DirectX-Headers, webauthn headers, `windows.0.52.0.lib` | GitHub (Microsoft), versions from ungoogled-chromium-windows | pinned commit / sha512 |
| clang, Rust, `rc`, sysroot, Node, PGO profile, ciopfs | Chromium's own storage buckets | sha1/sha256/md5 pinned by Chromium |
| Go (Dawn's source generators) | go.dev, version from Dawn's `go.mod` | sha256 from go.dev's index; the build runs with `GOTOOLCHAIN=local GOPROXY=off`, so Go never downloads anything itself |

Known quirks the script handles:

- Windows code includes headers with arbitrary casing (`ObjBase.h` for
  `objbase.h`). As in Chromium's own cross-build, the toolchain is served
  from a case-insensitive FUSE mount (ciopfs, binary pinned by Chromium):
  files are stored lower-cased in `winsysroot.ciopfs/` and mounted at
  `winsysroot/`. The mount is (re)created automatically before
  `toolchain`, `configure` and `build`, e.g. after a reboot.

- Microsoft's July 2026 SDK manifest has a raw space in one URL path
  (`w kits2`), which xwin rejects; the cached manifest is percent-encoded.
- `setup_toolchain.py` looks for `cl.exe` to find the VC bin directory. We
  build with clang-cl only, so an empty marker file is created; anything
  that tried to run it would fail loudly.
- gn loads the toolchain of every Windows CPU, so x86 and arm64 libraries
  are downloaded too.
- The PGO profile is stored gzip-compressed on GCS; its published md5 is the
  one of the compressed bytes.

## Not disturbing other services

The build host may also run production services. By default:

- every step runs at the lowest CPU priority (`nice 19`) and idle I/O
  priority (`ionice -c3`);
- the build runs inside a transient systemd scope with `CPUWeight=10`,
  `IOWeight=10` and a memory cap: the memory available when it starts minus
  16 GB left to the other services, at least 16 GB (`HB_MEM_MAX=26G` to fix
  it, `none` to disable). If a link outgrows the cap, the kernel kills the
  build, never another service;
- ninja runs one job per CPU and per 3 GB of that cap (`HB_JOBS` to change;
  `HB_KEEP_GOING=0` keeps going past failures to collect them all); a build
  that crashes is resumed once with half the jobs;
- compiles go through [ccache](https://ccache.dev) when it is installed
  (`cc_wrapper` in `args.gn`), with one cache for every build tree of the host
  (`/root/projects/hivey-ccache`, 150 GB; `HB_CCACHE_DIR`, `HB_CCACHE_SIZE`,
  `HB_CCACHE=0` to turn it off): a fresh tree of the same Chromium, or a
  rebuild after a change, recompiles only what changed. Changing a header
  that most of Chromium includes (`chrome_color_id.h`...) still rebuilds
  almost everything: Hivey patches avoid it;
- ThinLTO links use 4 threads instead of all hardware threads, on Windows
  and Linux (`hivey_thin_lto_jobs` in `flags.hivey.gn`, added by
  `patches/hivey/build/thin-lto-jobs-*.patch`).

`--full-priority` disables the priority changes.

## Branding

`brand/brand.json` is the single source of truth for the product identity:
product and company names, install and user-data paths
(`%LOCALAPPDATA%\Hivey\Browser\User Data`), ProgIDs, URL scheme, Active
Setup GUID. Icons (executable `.ico`, tiles, product logos, wordmark in
Space Grotesk, OFL-licensed in `brand/fonts/`) are rendered from
`brand/logo.svg`; this needs the Python packages `cairosvg` and `Pillow`.

User-visible strings are renamed **together with their translations**:
every `.xtb` translation is keyed by a fingerprint of the English text, so a
plain search-and-replace would silently drop all translations. `branding.py`
parses each `.grd` with Chromium's own grit before and after the rename and
re-keys the translations. "The Chromium Authors" is never renamed (BSD
attribution).

## Starting over

Domain substitution and branding rewrite files in place, so a hardlinked copy
of the tree is not a snapshot. To get a pristine tree, delete
`$HB_BUILD_DIR/src` and `.hb-state.json` (keep `download_cache/`, `tools/`,
`winsysroot/`, `xwin-cache/`) and run `hb.py all` again.

New Hivey patches can be added to an existing tree (`hb.py patch` applies
the ones not applied yet), but not while ninja runs: a new source file is
not in the running build's graph, and its final link would fail.
