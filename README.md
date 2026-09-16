# Visual Regression Testing

The rendered e-paper screen is tested by comparing it against golden PNGs
checked into `tests/images/`, rather than only asserting on the data that
feeds it. `tests/test_display_snapshots.py` builds each scenario (arrivals,
energy, weather, Spotify now-playing, empty states, etc.) directly from
representative data and renders it through the real `DisplayController`.

## Running it

```bash
pytest tests/test_display_snapshots.py
```

Compares each scenario's render against its golden image in `tests/images/`.
On a mismatch, the test fails with the actual render and a red-highlighted
diff written to `tests/images/_failures/<name>.actual.png` /
`<name>.diff.png` so you can see exactly what changed.

## Updating goldens after an intentional change

```bash
pytest tests/test_display_snapshots.py --update-snapshots
```

This only rewrites the golden images for scenarios whose render actually
changed -- `git status` afterwards shows exactly which ones. Review the new
PNGs, then commit them alongside your code change.

## Reviewing in a PR

Since the goldens are just PNGs committed to the repo, GitHub's own "Files
changed" view renders a visual diff (2-up / swipe / onion-skin) for any
changed image automatically -- no extra tooling needed. The loop is:
change code -> run tests (see what broke) -> `--update-snapshots` if the new
output is correct -> commit the changed PNGs -> open a PR -> review the
image diffs on GitHub -> merge.

## Adding a new scenario

Add a function to `tests/test_display_snapshots.py` that builds the panels
it needs and calls `snapshot.assert_matches("some_name", image)`. Run with
`--update-snapshots` once to create its golden image, review it, and commit
it.

# Deploying to a Raspberry Pi

Each tagged release publishes a wheel and a `countdown.service` unit to
GitHub Releases (see `.github/workflows/release.yml`). `packaging/install.sh`
downloads a release, installs it with `uv tool install`, and sets it up as a
systemd service:

```bash
curl -fsSL https://raw.githubusercontent.com/nvorkinn/countdown/main/packaging/install.sh | sudo bash
```

This installs `uv` for the invoking user if it isn't already present, and
runs the service as that user. Pass a release tag as an argument to install
a specific version instead of the latest, e.g. `sudo bash install.sh
v0.3.0`. Re-running the installer updates the app and restarts the service.

Every config field has a default, so the app runs right away with no config
file at all -- visit `http://<pi>:4000` and save settings there to write
`/opt/countdown/config.json` for the first time. Secrets can go in
`/opt/countdown/.env` instead (loaded the same way, from the service's
working directory).

Once installed:

```bash
systemctl status countdown   # check it's running
journalctl -u countdown -f   # tail its logs
```

The invoking user needs access to the e-paper hardware (typically the `gpio`
and `spi` groups on Raspberry Pi OS) for the display to actually render.
