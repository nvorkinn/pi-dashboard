import pytest

import countdown  # noqa: F401, I001 -- see test_display_snapshots.py for why this comes first
from countdown.core.api_registry import ClientClasses
from countdown.display_composers import COMPOSERS, choose_composer
from countdown.display_composers.base_composer import BaseComposer
from countdown.display_composers.glow_composer import GlowComposer
from countdown.display_composers.spotify_composer import SpotifyComposer
from countdown.display_composers.spotify_glow_composer import SpotifyGlowComposer

EVERYTHING = frozenset(ClientClasses)


@pytest.mark.parametrize(
    ("unavailable", "expected"),
    [
        (set(), SpotifyGlowComposer),
        ({ClientClasses.GLOWMARKT}, SpotifyComposer),
        ({ClientClasses.SPOTIFY}, GlowComposer),
        ({ClientClasses.SPOTIFY, ClientClasses.GLOWMARKT}, BaseComposer),
    ],
)
def test_choose_composer_makes_room_only_for_what_can_be_shown(unavailable, expected):
    assert type(choose_composer(EVERYTHING - unavailable)) is expected


def test_every_combination_of_spotify_and_glowmarkt_has_exactly_one_layout():
    """So the order of COMPOSERS doesn't matter, and the fallback is never needed."""
    optional = [ClientClasses.SPOTIFY, ClientClasses.GLOWMARKT]
    for spotify in (True, False):
        for glowmarkt in (True, False):
            unavailable = {api for api, on in zip(optional, (spotify, glowmarkt), strict=True) if not on}
            fitting = [c for c in COMPOSERS if c.can_compose(EVERYTHING - unavailable)]
            assert len(fitting) == 1, (spotify, glowmarkt, fitting)


def test_only_the_layout_without_spotify_or_glowmarkt_shows_four_stops():
    assert {type(c): c.stops_shown for c in COMPOSERS} == {
        SpotifyGlowComposer: 2,
        SpotifyComposer: 2,
        GlowComposer: 2,
        BaseComposer: 4,
    }
