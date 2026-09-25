from countdown.api_registry import ClientClasses
from countdown.display_composers.abstract_display_composer import AbstractDisplayComposer
from countdown.display_composers.spotify_composer import SpotifyComposer
from countdown.display_composers.spotify_glow_composer import SpotifyGlowComposer

# Tried in order, most specific first; a new layout is a new composer plus an entry here.
COMPOSERS: list[AbstractDisplayComposer] = [SpotifyComposer(), SpotifyGlowComposer()]
DEFAULT_COMPOSER = COMPOSERS[-1]


def choose_composer(available: frozenset[ClientClasses]) -> AbstractDisplayComposer:
    """The first layout that suits a device able to show `available`, falling back to the
    full one (which shows a message wherever a panel is missing)."""
    return next((composer for composer in COMPOSERS if composer.can_compose(available)), DEFAULT_COMPOSER)
