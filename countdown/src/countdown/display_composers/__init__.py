from countdown.api_registry import ClientClasses
from countdown.display_composers.abstract_display_composer import AbstractDisplayComposer
from countdown.display_composers.base_composer import BaseComposer
from countdown.display_composers.glow_composer import GlowComposer
from countdown.display_composers.spotify_composer import SpotifyComposer
from countdown.display_composers.spotify_glow_composer import SpotifyGlowComposer

# One per combination of Spotify and Glowmarkt.
DEFAULT_COMPOSER = SpotifyGlowComposer()
COMPOSERS: list[AbstractDisplayComposer] = [
    DEFAULT_COMPOSER,
    SpotifyComposer(),
    GlowComposer(),
    BaseComposer(),
]


def choose_composer(available: frozenset[ClientClasses]) -> AbstractDisplayComposer:
    """The layout that suits a device able to show `available`."""
    return next((composer for composer in COMPOSERS if composer.can_compose(available)), DEFAULT_COMPOSER)
