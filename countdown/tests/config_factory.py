from countdown.config_manager import AppConfig


def make_config(**overrides) -> AppConfig:
    """A complete, typical config for tests: what `AppConfig()` used to give before it
    lost its defaults. It goes through model_validate, the same strict path the broker's
    response takes, so a test can't build a config the broker couldn't have sent.
    Override a whole section with a dict, e.g. make_config(tfl={"stop_ids": ["940GZZLUKNG"]})."""
    typical = {
        "interval": 15,
        "tfl": {},
        "spotify": {},
        "weather": {},
        "glowmarkt": {},
        "pairing_code": None,
        "setup_missing": [],
    }
    return AppConfig.model_validate(typical | overrides)
