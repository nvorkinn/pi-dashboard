# pi-dashboard

[![codecov](https://codecov.io/gh/nvorkinn/pi-dashboard/graph/badge.svg)](https://codecov.io/gh/nvorkinn/pi-dashboard)

A Raspberry Pi e-paper dashboard and the telemetry that goes with it, in one
repo:

- [`countdown/`](countdown/) -- the long-running Python app that drives the
  display.
- [`pi-telemetry/`](pi-telemetry/) -- a short-lived Rust binary, run once a
  minute by a systemd timer, that reports Pi telemetry to Home Assistant over
  MQTT.
- Root -- `install.sh`, which provisions a Pi with both, and `secrets/`, the
  encrypted config it hands them.

The two apps are always deployed together and share config (`DEVICE_NAME` and
the MQTT settings in `/etc/pi-telemetry/env`), so they're released together:
one tag builds the countdown wheel, the pi-telemetry binary and the secrets
bundle, and `install.sh` installs exactly that tag. Each app is still its own
systemd unit, and its own installer can be used on its own.

Uses the [`gh` CLI](https://cli.github.com) (bootstrapped automatically if
missing) to resolve releases and download assets, since it handles
private-repo auth correctly on its own -- a hand-rolled `curl` approach
needs the asset API plus an `Accept` header, because a private repo's
`browser_download_url` doesn't work with a bearer token.

## Install

This repo is private, and fetching `install.sh` in the first place is also a
private-repo fetch, so you need a GitHub token with read access to it --
create one at
[github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens),
fine-grained, read-only, scoped to `pi-dashboard`. It has to be in your
shell *before* the very first `curl` that fetches this script.

Nothing here is ever fetched from `main` -- every fetch is pinned to a
specific tagged release. Check
[the releases page](https://github.com/nvorkinn/pi-dashboard/releases) for
the tag you want (there's no script running yet at the very first `curl` to
resolve "latest" for you, so it's the one place you look it up by hand) and
pass it explicitly, both in the URL and as the first argument. The script
installs exactly that release of both apps:

```sh
export GITHUB_TOKEN=github_pat_...
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
    https://raw.githubusercontent.com/nvorkinn/pi-dashboard/v1.0.0/install.sh \
    | sudo -E env GITHUB_TOKEN="$GITHUB_TOKEN" bash -s -- \
        v1.0.0 <device name>
```

`<device name>` is required -- see [Device name](#device-name) below.

The first run also asks for the age private key (see below) via a hidden
prompt. Both the GitHub token and the age key are cached under
`/etc/pi-setup` (root-only) afterwards, so re-running the installer with a
newer tag to update doesn't ask again -- except `GITHUB_TOKEN` still needs to
be in your environment for that first `curl`, since it happens before this
script (and its cache) exists.

## Updates

`install.sh` also installs `check_update.sh` (as
`/usr/local/sbin/pi-dashboard-check-update`) and a systemd timer that runs
it hourly from 02:00 to 06:00, then every three hours (09:00, 12:00, ...,
00:00). If the GitHub release marked "latest" isn't what's installed, it
downloads that release's `install.sh` and runs it with the cached token and
device name.

The release workflow creates every release as a pre-release, so nothing
reaches the Pis until you promote it:

    gh release edit v1.2.0 --prerelease=false --latest

(or tick "Set as the latest release" on its release page). To roll back,
mark an older release as latest the same way.

    systemctl list-timers pi-dashboard-update.timer
    journalctl -u pi-dashboard-update
    sudo pi-dashboard-check-update   # check now

## Releasing

Push a `v*` tag on a commit that's on `main`; `.github/workflows/release.yml`
builds everything and creates the GitHub release. The tag is the version of
both apps -- it's stamped into the wheel and the binary at build time, so the
`version` in `countdown/pyproject.toml` and `pi-telemetry/Cargo.toml` is just
a placeholder and doesn't need bumping.

Each app also has its own CI workflow that only runs when files under its
folder change (`.github/workflows/countdown-ci.yml`,
`.github/workflows/pi-telemetry-ci.yml`).

## Device name

Each Pi needs a name that identifies it in Home Assistant -- pick something
that says whose it is, e.g. `sister-hat`. It's the second argument to
`install.sh`. The name is sanitized (trimmed, lowercased, anything outside
`[a-z0-9_-]` becomes `-`, same rules as pi-telemetry's `device_name.rs`) and
written as `DEVICE_NAME=<name>` into `/etc/pi-telemetry/env`, which both apps'
systemd units load, replacing any `DEVICE_NAME` already there. It's also saved to `/etc/pi-setup/device-name`.
Releases before the rename called it `DEVICE_ID` (and `/etc/pi-setup/device-id`); both apps still read
`DEVICE_ID` when there's no `DEVICE_NAME`, and the next `install.sh` replaces both.

It isn't the `device_id` the auth broker gives a renderer when it registers.

Both apps use it in their MQTT client ID and topics, and pi-telemetry in its
HA device, so their data lands under the same device in Home Assistant.
Don't put `DEVICE_NAME` in the encrypted secrets -- they're shared by every
Pi, and `install.sh` overwrites it anyway.

Re-running with a different name changes it, and HA will treat it as a
new device (the old one's entities are orphaned), so `install.sh` warns
when that happens. Re-run with the same name to keep it.

## How secrets work

Each app's real secrets file (countdown's `.env`, pi-telemetry's
`/etc/pi-telemetry/env`) is encrypted with [age](https://age-encryption.org)
and committed here as `secrets/<app>.env.age`. `install.sh` gets them from
the `secrets.zip` release asset (built by `.github/workflows/release.yml`)
via `gh release download`, not a direct file fetch. There's one keypair for
all of it:

- **Public key** -- safe to share, used to encrypt. Currently:
  `age1mrlql83ne3jewsuqzemmlrxsdscn9sqlksl4uqhy8da5krn75usq5u46ak`
- **Private key** -- decrypts everything. Lives only in
  `local-only/age-key.txt` on this machine (gitignored -- never committed)
  and cached at `/etc/pi-setup/age-key.txt` on each provisioned Pi. **Back
  this up somewhere outside git** (a password manager entry is enough) --
  if it's lost, every encrypted secret in this repo becomes unrecoverable
  and has to be re-created and re-encrypted from scratch.

If a given `secrets/<app>.env.age` doesn't exist yet, `install.sh` skips it
and that app falls back to its own defaults (countdown gets its config from
auth-broker anyway; pi-telemetry seeds a placeholder env you have to edit by
hand).

### Adding or updating a secret

Edit the real file locally (e.g. a scratch copy of countdown's `.env` or
pi-telemetry's `pi-telemetry/systemd/env.example` filled in with real values), then:

```sh
age -e -r age1mrlql83ne3jewsuqzemmlrxsdscn9sqlksl4uqhy8da5krn75usq5u46ak \
    -o secrets/countdown.env.age /path/to/real/.env

age -e -r age1mrlql83ne3jewsuqzemmlrxsdscn9sqlksl4uqhy8da5krn75usq5u46ak \
    -o secrets/pi-telemetry.env.age /path/to/real/env
```

Commit the resulting `.age` file. It's ciphertext -- safe in git even
though the repo is private anyway. Since `install.sh` only ever reads
secrets from the release tag it was fetched at, a new secret doesn't take
effect anywhere until you **cut a new release** (push a new tag) and re-run
the installer against it. It also won't overwrite pi-telemetry's env if one
already exists on disk -- delete `/etc/pi-telemetry/env` on the Pi first if
you want the new encrypted value to actually take effect there.

### Rotating the age key

Generate a new keypair (`age-keygen -o local-only/age-key.txt`), re-encrypt
every `secrets/*.age` file with the new public key, update the public key
in this README, and update `/etc/pi-setup/age-key.txt` on every Pi (or just
delete it there so the installer prompts for the new one on next run).

## What this does and doesn't protect against

Secrets are encrypted at rest in git and in transit, but once decrypted
onto a Pi they live as plain files (`chmod 600`, owned by the service
user) -- that's what `EnvironmentFile=`/`.env` loading requires. That's the
standard baseline for this kind of setup: it stops other unprivileged users
on the box and accidental exposure via git. It does **not** protect against
someone with root on the Pi, or someone with the physical SD card -- file
permissions don't apply once you're not going through the OS that set them.
