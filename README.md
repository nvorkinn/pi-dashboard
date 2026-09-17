# pi-setup

One script that provisions a Raspberry Pi with both
[countdown](https://github.com/nvorkinn/countdown) and
[pi-telemetry](https://github.com/nvorkinn/pi-telemetry), each installed via
its own release and set up as its own systemd unit. It also hands each app
its real secrets, decrypted from this repo, so you don't have to copy
`.env`/`env` files onto every Pi by hand.

## Install

All three repos involved here are private -- `nvorkinn/countdown`,
`nvorkinn/pi-telemetry`, and this repo itself, since fetching `install.sh`
in the first place is also a private-repo fetch. So you need one GitHub
token with read access to **all three**, not just the two apps -- create
one at
[github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens),
fine-grained, read-only, scoped to `countdown`, `pi-telemetry`, and
`pi-setup`. It has to be in your shell *before* the very first `curl` that
fetches this script.

Nothing here is ever fetched from `main` -- every fetch is pinned to a
specific tagged release, including `pi-setup`'s own `install.sh`. Check
[the releases page](https://github.com/nvorkinn/pi-setup/releases) for the
current tag (there's no script running yet at the very first `curl` to
resolve "latest" for you, so it's the one place you look it up by hand) and
pass it explicitly, both in the URL and as the first argument:

```sh
export GITHUB_TOKEN=github_pat_...
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
    https://raw.githubusercontent.com/nvorkinn/pi-setup/v1.0.0/install.sh \
    | sudo -E env GITHUB_TOKEN="$GITHUB_TOKEN" bash -s -- \
        v1.0.0 [countdown_version] [pi_telemetry_version]
```

`countdown_version`/`pi_telemetry_version` are release tags too (e.g.
`v0.3.1`), but *those* don't need a manual lookup -- both default to
`latest`, resolved automatically via the releases API once `install.sh` is
actually running.

The first run also asks for the age private key (see below) via a hidden
prompt. Both the GitHub token and the age key are cached under
`/etc/pi-setup` (root-only) afterwards, so re-running the installer to
update doesn't ask again -- except `GITHUB_TOKEN` still needs to be in your
environment for that first `curl`, since it happens before this script (and
its cache) exists.

## How secrets work

Each app's real secrets file (countdown's `.env`, pi-telemetry's
`/etc/pi-telemetry/env`) is encrypted with [age](https://age-encryption.org)
and committed here as `secrets/<app>.env.age`. There's one keypair for all
of it:

- **Public key** -- safe to share, used to encrypt. Currently:
  `age1mrlql83ne3jewsuqzemmlrxsdscn9sqlksl4uqhy8da5krn75usq5u46ak`
- **Private key** -- decrypts everything. Lives only in
  `local-only/age-key.txt` on this machine (gitignored -- never committed)
  and cached at `/etc/pi-setup/age-key.txt` on each provisioned Pi. **Back
  this up somewhere outside git** (a password manager entry is enough) --
  if it's lost, every encrypted secret in this repo becomes unrecoverable
  and has to be re-created and re-encrypted from scratch.

If a given `secrets/<app>.env.age` doesn't exist yet, `install.sh` skips it
and that app falls back to its own defaults (countdown runs with no config
until you set it via its web UI; pi-telemetry seeds a placeholder env you
have to edit by hand).

### Adding or updating a secret

Edit the real file locally (e.g. a scratch copy of countdown's `.env` or
pi-telemetry's `systemd/env.example` filled in with real values), then:

```sh
age -e -r age1mrlql83ne3jewsuqzemmlrxsdscn9sqlksl4uqhy8da5krn75usq5u46ak \
    -o secrets/countdown.env.age /path/to/real/.env

age -e -r age1mrlql83ne3jewsuqzemmlrxsdscn9sqlksl4uqhy8da5krn75usq5u46ak \
    -o secrets/pi-telemetry.env.age /path/to/real/env
```

Commit the resulting `.age` file. It's ciphertext -- safe in git even
though the repo is private anyway. Since `install.sh` only ever reads
secrets from the pinned `PISETUP_TAG` it was fetched at, a new secret
doesn't take effect anywhere until you **cut a new pi-setup release**
(tag + `gh release create`) and re-run the installer against that new tag
(or just use `latest`). It also won't overwrite pi-telemetry's env if one
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
