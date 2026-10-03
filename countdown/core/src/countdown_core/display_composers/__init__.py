from countdown_core.core.api_registry import ClientClasses
from countdown_core.display_composers.abstract_display_composer import AbstractDisplayComposer
from countdown_core.display_composers.base_composer import BaseComposer
from countdown_core.display_composers.glow_composer import GlowComposer
from countdown_core.display_composers.spotify_composer import SpotifyComposer
from countdown_core.display_composers.spotify_glow_composer import SpotifyGlowComposer

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
