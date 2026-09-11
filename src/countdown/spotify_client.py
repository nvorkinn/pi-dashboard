import spotipy
from spotipy.oauth2 import SpotifyOAuth

class SpotifyClient:
    def __init__(self, config: dict) -> None:
        self.spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=config.get("clientID"),
        client_secret=config.get("clientSecret"),
        redirect_uri=config.get("redirectUrl"),
        scope="user-read-currently-playing user-read-playback-state",
        cache_path=".spotify_token_cache",
        open_browser=False
    ))

    def get_current_track(self) -> dict[str, str] | None:
        """Retrieves the currently playing song, artist, and playback status."""
        try:
            current_playback = self.spotify.current_playback()

            if not current_playback or not current_playback.get("item"):
                return None

            track = current_playback["item"]
            return {
                "song": track["name"],
                "artist": ", ".join(artist["name"] for artist in track["artists"]),
                "album": track["album"]["name"],
                "album_image": min(track["album"]["images"], key=lambda image: image["height"])["url"],
                "is_playing": current_playback["is_playing"]
            }
        except Exception as e:
            print(f"API Error: {e}")
            return None
