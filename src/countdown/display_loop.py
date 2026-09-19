import time

import pydantic
import requests

from countdown.api_registry import ApiRegistry
from countdown.broker_client import BrokerClient
from countdown.config_manager import (
    AppConfig,
    GlowmarktConfig,
    TflConfig,
    WeatherConfig,
)
from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.weather_client import WeatherClient
from display.display import DisplayController
from display.pairing_code_panel import PairingCodePanel


def safe_fetch(func, fallback):
    try:
        return func()
    except requests.exceptions.RequestException as e:
        print(f"Exception with API call to Glowmarkt: {e}")
        return fallback
    except pydantic.ValidationError as e:
        print(f"Pydantic validation error: {e}")
        return fallback


class DisplayLoop:
    """Owns everything needed to run one refresh cycle, plus everything that needs to
    survive between cycles -- last-known energy readings/track/weather panel, so a
    failed fetch can keep showing stale-but-valid data instead of nothing. EnergyPanel
    itself isn't cached: it's cheap to build (no I/O, no rendering happens until
    display.py calls .render()), so it's rebuilt on demand from self.energy rather
    than kept as separate, redundant state -- current_track already works this way.

    broker/config/pairing_code_panel are required, not optional-with-a-computed-
    fallback: the caller (see fetch_app_config()) resolves them before
    construction, so this class never has an implicit "figure it out myself"
    branch to get wrong."""

    def __init__(
        self,
        broker: BrokerClient,
        config: AppConfig,
        pairing_code_panel: PairingCodePanel,
        display: DisplayController | None = None,
    ):
        self.broker = broker
        self.config = config
        self.pairing_code_panel = pairing_code_panel
        self.interval = config.interval
        self.display = display if display is not None else DisplayController()
        self.api_reg = ApiRegistry()
        # Unlike tfl/weather, resolving a Glowmarkt resource id means actually
        # authenticating against Glowmarkt's own API, not just reading a value out
        # of config -- deferred to run(), retried lazily each full-refresh cycle via
        # safe_fetch, so a missing/not-yet-set-up credential doesn't tie this
        # constructor's success to a third-party API being up, and doesn't
        # crash-loop on every restart the way an eager, unguarded call here once did.

    async def run(self) -> None:
        self.api_reg.build_from_config(self.config)
        await self.api_reg.authenticate_all()
        while True:
            try:
                if self.pairing_code_panel.pairing_code:
                    # Only repaint when the code actually changes (BrokerClient's own
                    # cache decides that, see get_pairing_code_panel) -- this is a full
                    # e-paper refresh, and a gifted device can sit unpaired for hours
                    # or days; repainting an identical screen every cycle for that
                    # whole window is avoidable hardware wear, not just noise.
                    if self.pairing_code_panel.has_changed:
                        self.display.display_pairing_screen(self.pairing_code_panel)
                else:
                    panels = await self.api_reg.update_all()
                    self.display.display_screen(panels)
            except requests.exceptions.RequestException as e:
                print(f"Network error encountered: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")

            time.sleep(self.interval)
            self.refresh_broker_config()

            if not self.interval:
                break

    def refresh_broker_config(self) -> None:
        """Polls the broker's per-device config every cycle -- it's the only way to
        find out something changed, since the broker exposes no change-timestamp.
        Also where pairing_code gets kept current, same call, no separate poll.
        Only mutates/rebuilds what actually differs (building a fresh TflClient can
        never fail: construction does no network I/O, stop resolution is retried
        lazily and safely on next use -- but it would force needless stop-resolution
        calls against the TfL API every cycle if rebuilt unconditionally)."""
        fetched = safe_fetch(lambda: self.broker.get_config(), None)
        if fetched is None:
            return

        self.pairing_code_panel = self.broker.get_pairing_code_panel(fetched)

        # Compared via model_dump() rather than `fetched.tfl == self.config.tfl`:
        # fetched.tfl is a BrokerTflConfig (parsed from the wire response) and
        # self.config.tfl is a TflConfig -- different pydantic classes with the same
        # shape, and pydantic's BaseModel.__eq__ checks the class too, so a direct
        # == would always be False regardless of the actual data, forcing a
        # rebuild every single cycle. Comparing dicts sidesteps that, and also
        # means adding a field to a *Config later doesn't need this method updated.
        if fetched.tfl.model_dump() != self.config.tfl.model_dump():
            self.config.tfl = TflConfig(**fetched.tfl.model_dump())
            self.tfl = TflClient(self.config.tfl)

        if fetched.weather.model_dump() != self.config.weather.model_dump():
            self.config.weather = WeatherConfig(**fetched.weather.model_dump())
            self.weather = WeatherClient(self.config.weather)

        if fetched.glowmarkt.model_dump() != self.config.glowmarkt.model_dump():
            self.config.glowmarkt = GlowmarktConfig(**fetched.glowmarkt.model_dump())
            self.glow = GlowClient(self.config.glowmarkt)

        self.config.interval = fetched.interval
        self.interval = fetched.interval
        self.config.spotify.enabled = fetched.spotify.enabled
