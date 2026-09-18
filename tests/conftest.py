from pathlib import Path

import pytest
from PIL import Image

from test_utils import highlight_diff, images_equal

# Env vars AppConfig reads via pydantic-settings (see config_manager.py). Cleared so a
# developer's real .env values can never leak into a test run. Note LiveConfig is
# deliberately NOT on this list -- it's a plain BaseModel, not BaseSettings, so it
# never reads the environment at all (see test_live_config_ignores_env_vars).
_APP_CONFIG_ENV_VARS = [
    "BROKER_URL",
    "GLOWMARKT__USERNAME", "GLOWMARKT__PASSWORD",
]


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Run every test in an empty temp directory with no app env vars set, so nothing
    can accidentally read (or write into) the real project's .env, or any device-local
    file a test writes into this same tmp_path (e.g. .auth_broker_device)."""
    monkeypatch.chdir(tmp_path)
    for key in _APP_CONFIG_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


# --- Visual regression snapshots -------------------------------------------------
# Golden images live in tests/images/, addressed by __file__ (not cwd) so they're
# unaffected by isolated_cwd's chdir above.
SNAPSHOT_DIR = Path(__file__).parent / "images"
FAILURE_DIR = SNAPSHOT_DIR / "_failures"

# Pillow's text/icon rasterization can differ by a handful of anti-aliased pixels
# between platforms (observed: goldens generated on macOS/arm64 failed on CI's
# ubuntu-latest) even with byte-identical fonts and code -- a pure pixel-exact
# compare is too strict across machines. A real layout/content regression moves
# far more pixels by far more than this, so a small tolerance still catches those
# while absorbing rendering noise.
DEFAULT_SNAPSHOT_THRESHOLD = 0.005


def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Write tests/images/ golden files from the current render instead of "
             "comparing against them. Review the resulting diff before committing.",
    )


class Snapshot:
    def __init__(self, update: bool):
        self.update = update

    def assert_matches(self, name: str, image: Image.Image, threshold: float = DEFAULT_SNAPSHOT_THRESHOLD) -> None:
        golden_path = SNAPSHOT_DIR / f"{name}.png"
        failure_actual = FAILURE_DIR / f"{name}.actual.png"
        failure_diff = FAILURE_DIR / f"{name}.diff.png"
        actual = image.convert("RGB")

        if self.update:
            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            actual.save(golden_path)
            failure_actual.unlink(missing_ok=True)
            failure_diff.unlink(missing_ok=True)
            return

        if not golden_path.exists():
            pytest.fail(
                f"No snapshot for '{name}' yet at {golden_path}. Run "
                "`pytest --update-snapshots`, review the generated image, then commit it."
            )

        golden = Image.open(golden_path).convert("RGB")
        if images_equal(golden, actual, threshold=threshold):
            failure_actual.unlink(missing_ok=True)
            failure_diff.unlink(missing_ok=True)
            return

        FAILURE_DIR.mkdir(parents=True, exist_ok=True)
        actual.save(failure_actual)
        diff_note = ""
        if golden.size == actual.size:
            highlight_diff(golden, actual).save(failure_diff)
            diff_note = f" and diff (changed pixels in red) at {failure_diff}"

        pytest.fail(
            f"Rendered output for '{name}' no longer matches tests/images/{name}.png.\n"
            f"Actual render saved to {failure_actual}{diff_note}.\n"
            "If this change is intentional, run `pytest --update-snapshots`, review "
            "the new image, and commit it."
        )


@pytest.fixture
def snapshot(request) -> Snapshot:
    return Snapshot(update=request.config.getoption("--update-snapshots"))
