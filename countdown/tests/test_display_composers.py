import pytest

import countdown  # noqa: F401, I001 -- see test_display_snapshots.py for why this comes first
from countdown.api_registry import ClientClasses
from countdown.display_composers import choose_composer
from countdown.display_composers.spotify_composer import SpotifyComposer
from countdown.display_composers.spotify_glow_composer import SpotifyGlowComposer

EVERYTHING = frozenset(ClientClasses)


@pytest.mark.parametrize(
    ("unavailable", "expected"),
    [
        (set(), SpotifyGlowComposer),
        ({ClientClasses.GLOWMARKT}, SpotifyComposer),
        # No Spotify-less layout yet: the full one, with Spotify's area saying so.
        ({ClientClasses.SPOTIFY}, SpotifyGlowComposer),
        # Glow's column goes; Spotify's strip says it isn't set up.
        ({ClientClasses.SPOTIFY, ClientClasses.GLOWMARKT}, SpotifyComposer),
    ],
)
def test_choose_composer_makes_room_only_for_what_can_be_shown(unavailable, expected):
    assert type(choose_composer(EVERYTHING - unavailable)) is expected
