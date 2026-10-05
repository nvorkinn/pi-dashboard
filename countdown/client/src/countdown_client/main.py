import asyncio
import logging
import os

from countdown_client.client import Client


def configure_logging() -> None:
    """Same as countdown_core's: no timestamp, since journald adds its own. An unrecognised
    LOG_LEVEL falls back to INFO."""
    level = logging.getLevelNamesMapping().get(os.environ.get("LOG_LEVEL", "").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s",
    )


def run() -> None:
    configure_logging()
    client = Client()
    asyncio.run(client.start())


if __name__ == "__main__":
    run()
