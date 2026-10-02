from countdown.config_server.models import AppConfig


def make_config(**overrides) -> AppConfig:
    """A complete, typical config, validated the same way as the broker's response.
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
