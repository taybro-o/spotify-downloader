"""
Saved module for handing the saved tracks from user library
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from spotdl.types.song import Song, SongList
from spotdl.utils.spotify import SpotifyClient

__all__ = ["Saved", "SavedError"]

logger = logging.getLogger(__name__)

EXPORTIFY_HELP_MESSAGE = """
╔══════════════════════════════════════════════════════════════════════╗
║  SPOTIFY API ERROR: Cannot fetch saved/liked tracks (HTTP 403)     ║
║                                                                    ║
║  This happens because Spotify's Web API requires the app owner     ║
║  to have Spotify Premium to access /me/tracks.                     ║
║                                                                    ║
║  WORKAROUND — Use Exportify to export your liked songs:            ║
║                                                                    ║
║  1. Go to https://exportify.net                                    ║
║  2. Log in with your Spotify account                               ║
║  3. Export your "Liked Songs" playlist as a CSV file                ║
║  4. Run: spotdl download --from-csv exported.csv                   ║
║                                                                    ║
║  This will download all your liked songs with full metadata,       ║
║  no Premium required!                                              ║
╚══════════════════════════════════════════════════════════════════════╝
"""


class SavedError(Exception):
    """
    Base class for all exceptions related to saved tracks.
    """


@dataclass(frozen=True)
class Saved(SongList):
    """
    Saved class for handling the saved tracks from user library.
    """

    @staticmethod
    def get_metadata(url: str = "saved") -> Tuple[Dict[str, Any], List[Song]]:
        """
        Returns metadata for a saved list.

        ### Arguments
        - url: Not required, but used to match the signature of the other get_metadata methods.

        ### Returns
        - metadata: A dictionary containing the metadata for the saved list.
        - songs: A list of Song objects.

        ### Raises
        - SavedError: If the Spotify API returns 403 (Premium required) or
          any other error. The error message includes instructions to use
          Exportify as a workaround.
        """

        metadata = {"name": "Saved tracks", "url": url}

        spotify_client = SpotifyClient()
        if spotify_client.user_auth is False:  # type: ignore
            raise SavedError("You must be logged in to use this function")

        try:
            saved_tracks_response = spotify_client.current_user_saved_tracks()
        except Exception as exc:
            exc_str = str(exc).lower()

            # Catch HTTP 403 Forbidden — Premium required
            if "403" in exc_str or "forbidden" in exc_str:
                logger.error(EXPORTIFY_HELP_MESSAGE)
                raise SavedError(
                    "Spotify API returned 403 Forbidden when fetching saved tracks. "
                    "This typically means the app owner's Spotify account does not "
                    "have Premium. Use Exportify (https://exportify.net) to export "
                    "your liked songs as a CSV, then run:\n\n"
                    "    spotdl download --from-csv your_export.csv\n"
                ) from exc

            # Catch HTTP 401 Unauthorized — token expired or invalid
            if "401" in exc_str or "unauthorized" in exc_str:
                logger.error(
                    "Spotify API returned 401 Unauthorized. "
                    "Your auth token may have expired. Try logging in again "
                    "with --user-auth, or use Exportify as a workaround."
                )
                raise SavedError(
                    "Spotify API returned 401 Unauthorized. "
                    "Try re-authenticating with --user-auth, or use:\n\n"
                    "    spotdl download --from-csv your_export.csv\n"
                ) from exc

            # Re-raise other exceptions with helpful context
            logger.error(
                "Failed to fetch saved tracks from Spotify API: %s\n"
                "If this persists, try using Exportify as a workaround:\n"
                "    spotdl download --from-csv your_export.csv",
                exc,
            )
            raise SavedError(
                f"Failed to fetch saved tracks: {exc}\n\n"
                "If this error persists, use Exportify (https://exportify.net) "
                "to export your liked songs, then run:\n\n"
                "    spotdl download --from-csv your_export.csv\n"
            ) from exc

        if saved_tracks_response is None:
            raise SavedError("Couldn't get saved tracks")

        saved_tracks = saved_tracks_response["items"]

        # Fetch all saved tracks
        while saved_tracks_response and saved_tracks_response["next"]:
            response = spotify_client.next(saved_tracks_response)
            if response is None:
                break

            saved_tracks_response = response
            saved_tracks.extend(saved_tracks_response["items"])

        songs = []
        for track in saved_tracks:
            if not isinstance(track, dict):
                continue

            # Support both old API (track) and new API (item)
            track_meta = track.get("track") or track.get("item")
            if track_meta is None or track_meta.get("is_local"):
                continue

            album_meta = track_meta["album"]

            release_date = album_meta["release_date"]
            artists = artists = [artist["name"] for artist in track_meta["artists"]]

            song = Song.from_missing_data(
                name=track_meta["name"],
                artists=artists,
                artist=artists[0],
                album_id=album_meta["id"],
                album_name=album_meta["name"],
                album_artist=album_meta["artists"][0]["name"],
                album_type=album_meta["album_type"],
                disc_number=track_meta["disc_number"],
                duration=int(track_meta["duration_ms"] / 1000),
                year=release_date[:4],
                date=release_date,
                track_number=track_meta["track_number"],
                tracks_count=album_meta["total_tracks"],
                song_id=track_meta["id"],
                explicit=track_meta["explicit"],
                url=track_meta["external_urls"]["spotify"],
                isrc=track_meta.get("external_ids", {}).get("isrc"),
                cover_url=(
                    max(album_meta["images"], key=lambda i: i["width"] * i["height"])[
                        "url"
                    ]
                    if album_meta["images"]
                    else None
                ),
            )

            songs.append(song)

        return metadata, songs
