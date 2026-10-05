from countdown_core.core.app import main
from countdown_standalone.epd_target import target_from_env


def run() -> None:
    """The `countdown-standalone` console script: the app, painting on the Pi's own panel."""
    main(lambda _registration: target_from_env(), standalone=True)


if __name__ == "__main__":
    run()
