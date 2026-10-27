# Releases and updates

Chromium ships security fixes every week or two. A browser that lags behind
is not private, whatever its settings, so Hivey Browser follows Chromium
without anyone having to start a build.

## Versions

`chrome/VERSION` is Chromium's version with the Hivey revision
(`HIVEY_REVISION`, 1 to 99) in the last field: `PATCH = upstream PATCH × 100 +
revision`. Chromium 156.0.8078.47 with revision 1 is **156.0.8078.4701**. A
change to Hivey alone (same Chromium) bumps `HIVEY_REVISION`, so it installs
as an update. Web pages still see 156.0.8078.47, like every other Chromium
user (`patches/hivey/build/hivey-updater.patch`).

## The automatic pipeline

`scripts/autoupdate.py` runs every 5 minutes on the build host (systemd
timer, installed by `scripts/install-autoupdate.sh`): a run that finds nothing
new is a few GitHub API calls, so an update starts building within minutes of
its release. It works in its own clone (reset to `origin/main` before each
run, so merged changes to the pipeline apply by themselves) and build tree,
at the lowest CPU and I/O priority.

1. **New Chromium?** It takes the newest ungoogled-chromium release that
   ungoogled-chromium-windows also supports (same Chromium version), and
   prepares branch `auto/chromium-<version>`: submodules bumped,
   `HIVEY_REVISION` back to 1, patches checked against the new source tarball
   and refreshed if they only moved (`scripts/patchcheck.py --refresh`). A
   patch that no longer applies stops here: that needs a human.
   **New Hivey AI sidebar?** The sidebar follows the `main` branch of
   [HiveyAI-Sidebar](https://github.com/FlorianMartins/HiveyAI-Sidebar): when
   it has a newer commit whose checks all passed, the submodule moves to it
   (in the Chromium branch, or in `auto/hivey-ai-<commit>` with
   `HIVEY_REVISION` bumped). `CHANGELOG.md` gets the new version's entry.
   Not every commit is worth a release: the sidebar's daily model catalogue
   update (`chore(models): daily auto-update…`, prices and context windows;
   the model lists themselves are fetched live) waits for the next real
   change, or ships after 7 days at most; a real change waits until it has
   been quiet for 30 minutes, so a series of merges makes one release.
2. **Build.** Fresh tree, Windows and Linux, packages (`hb.py package`).
   Compile jobs follow the memory the host can spare (about 3 GB each,
   within a cap of the available memory minus 16 GB; `HB_JOBS` and
   `HB_MEM_MAX` override), compiles go through a ccache shared by every
   build tree, and a build that crashes is resumed once with half the jobs.
3. **Draft release** (`scripts/release.py draft`): installers, `SHA256SUMS`,
   and the signed update manifest.
4. **Checks.** Linux on the build host, Windows on a GitHub runner
   (`.github/workflows/windows-smoke.yml`, which installs the draft): no
   request at startup on a fresh profile (`tests/startup_requests.py`), then
   the privacy checks over DevTools (`tests/cdp_checks.py`).
5. **Ship.** Only if every check passes: the branch is merged through a pull
   request (its checks include the Windows smoke test of the draft) and the
   release is published.
6. **Dev channel.** The `dev` pre-release is then replaced with this build
   of main. When only main changed (no new version), the nightly run still
   rebuilds it, checks it on Linux and replaces `dev`.

Any failure opens (or comments on) a GitHub issue labelled `autoupdate`, with
the end of the log. The same update is not retried until something new comes
(a Chromium release, a sidebar commit or a change on main).

Every pull request that touches patches or submodules also runs
`patchcheck.py` in CI (`.github/workflows/patch-stack.yml`, about two
minutes, no build).

## Dev builds

Permanent links to the latest build of main, for testing before a release
(installed browsers never take them: a pre-release is never "latest"):

- Windows: <https://github.com/FlorianMartins/hivey-browser/releases/download/dev/hivey-browser-dev-windows-x64-installer.exe>
- Linux: <https://github.com/FlorianMartins/hivey-browser/releases/download/dev/hivey-browser-dev-linux-x64.tar.xz>

## Changelog

Every change users notice gets a French, user-facing entry in
[CHANGELOG.md](../CHANGELOG.md) in the same pull request, under the version
it ships in; `release.py` puts that section at the top of the release notes
and of the dev pre-release.

## How browsers update

The update check (`chrome/browser/hivey/hivey_updater.cc`):

- never runs at startup: first 10 minutes after launch, then every 12 hours,
  and not at all when *Hivey Settings > About > Automatic updates* is off;
- downloads `hivey-update.json` and `hivey-update.json.sig` from the latest
  **published** release (drafts are invisible), without cookies;
- accepts the manifest only if its **Ed25519** signature matches the public
  key compiled into the browser;
- on Windows (per-user install), downloads the installer named in the
  manifest, which must come from this repository's releases and match the
  size and **sha256** in the signed manifest, runs it silently, and the
  browser then offers *Relaunch to update*;
- on Linux (portable package) and system-wide Windows installs, shows the new
  version in Hivey Settings with a link to the release.

## Keys

Two private keys live on the release machine, outside the repository, mode
0600. `hb.py bundle` creates them the first time:

| Key | Default path | Used for |
| --- | --- | --- |
| Update signing (Ed25519) | `~/.config/hivey/update-signing.pem` (`HB_UPDATE_KEY`) | signs `hivey-update.json`; its public half is built into the browser |
| Bundled extensions (RSA) | `~/.config/hivey/bundled-extensions.pem` (`HB_EXTENSION_KEY`) | signs the bundled uBlock Origin Lite `.crx`; it decides the extension ID |

Losing the update key means installed browsers stop accepting updates (users
must reinstall once). Changing the extension key changes the extension ID,
so installed browsers would get a second copy. Back both up.

## By hand

```bash
python3 scripts/autoupdate.py --dry-run        # what would happen
python3 scripts/release.py draft               # after hb.py package (both targets)
gh workflow run windows-smoke.yml -f tag=v156.0.8078.4701
python3 scripts/release.py publish --tag v156.0.8078.4701
```
