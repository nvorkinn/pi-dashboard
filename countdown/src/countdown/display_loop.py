import asyncio
import logging
import time
from datetime import UTC, datetime

import pydantic
import requests

from countdown.api_registry import ApiRegistry
from countdown.broker_client import BrokerClient
from countdown.config_manager import (
    AppConfig,
)
from display.display import DisplayController
from display.pairing_code_panel import PairingCodePanel
from display.setup_panel import SetupPanel

logger = logging.getLogger(__name__)


def safe_fetch(func, fallback):
    try:
        return func()
    except requests.exceptions.RequestException as e:
        logger.exception(f"Exception with API call to Glowmarkt: {e}")
        return fallback
    except pydantic.ValidationError as e:
        logger.exception(f"Pydantic validation error: {e}")
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
        api_reg: ApiRegistry | None = None,
    ):
        self.broker = broker
        self.config = config
        self.pairing_code_panel = pairing_code_panel
        self.interval = config.interval
        # self.interval = 60 # config.interval
        self.display = display if display is not None else DisplayController()
        self.api_reg = api_reg if api_reg is not None else ApiRegistry()
        self._setup_shown: list[str] | None = None
        self._published_stage: str | None = None
        # Unlike tfl/weather, resolving a Glowmarkt resource id means actually
        # authenticating against Glowmarkt's own API, not just reading a value out
        # of config -- deferred to run(), retried lazily each full-refresh cycle via
        # safe_fetch, so a missing/not-yet-set-up credential doesn't tie this
        # constructor's success to a third-party API being up, and doesn't
        # crash-loop on every restart the way an eager, unguarded call here once did.

    async def run(self) -> None:
        started = time.monotonic()
        await self.api_reg.on_config_update(self.config)
        first_cycle_done = False
        while True:
            try:
                if self.pairing_code_panel.pairing_code:
                    self.api_reg.status.stage = "pairing"
                    self._setup_shown = None
                    # Only repaint when the code actually changes (BrokerClient's own
                    # cache decides that, see get_pairing_code_panel) -- this is a full
                    # e-paper refresh, and a gifted device can sit unpaired for hours
                    # or days; repainting an identical screen every cycle for that
                    # whole window is avoidable hardware wear, not just noise.
                    if self.pairing_code_panel.has_changed:
                        self.display.display_pairing_screen(self.pairing_code_panel)
                elif self.config.setup_missing:
                    self.api_reg.status.stage = "setup"
                    if self.config.setup_missing != self._setup_shown:
                        self.display.display_setup_screen(SetupPanel(self.config.setup_missing))
                        self._setup_shown = list(self.config.setup_missing)
                else:
                    self.api_reg.status.stage = "running"
                    self._setup_shown = None
                    panels = await self.api_reg.update_all()
                    self.display.display_screen(panels)
                self.display.repaint_pending()
            except requests.exceptions.RequestException as e:
                logger.exception(f"Network error encountered: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error: {e}")

            stage = self.api_reg.status.stage
            await self.api_reg.publish_health(force=stage != self._published_stage)
            self._published_stage = stage

            if not first_cycle_done:
                # Once, not every cycle: how long the device took to get its first screen up
                # (client set-up included), to spot a slow start without spamming the journal.
                logger.info(f"First cycle finished {time.monotonic() - started:.1f}s after start")
                first_cycle_done = True

            # Not time.sleep(): that would freeze the event loop for the whole interval.
            await asyncio.sleep(self.interval)
            await self.refresh_broker_config()

            if not self.interval:
                break

    async def refresh_broker_config(self) -> None:
        """Polls the broker's per-device config every cycle -- it's the only way to
        find out something changed, since the broker exposes no change-timestamp.
        Also where pairing_code gets kept current, same call, no separate poll.
        Deciding what a config change means for each API is the registry's (and the
        clients') job, not this loop's -- see ApiRegistry.on_config_update()."""
        fetched = safe_fetch(lambda: self.broker.get_config(), None)
        if fetched is None:
            return

        self.pairing_code_panel = self.broker.get_pairing_code_panel(fetched)
        self.api_reg.status.last_broker_sync = datetime.now(UTC)
        self.config = fetched
        self.interval = fetched.interval
        await self.api_reg.on_config_update(fetched)
