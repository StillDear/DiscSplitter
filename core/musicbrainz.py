"""The MusicBrainz web service: rate-limited requests, release search, picking a disc of a release."""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from . import appinfo
from .jobs import Failure
from typing import Optional



# ---------------------------------------------------------------------------
# The MusicBrainz web service: rate-limited requests and release search.
# metadata_sources puts it behind the same search/fetch interface as the
# other catalogues.
# ---------------------------------------------------------------------------

MUSICBRAINZ_BASE_URL = "https://musicbrainz.org/ws/2"
# MusicBrainz's API policy requires a descriptive User-Agent identifying
# the application and a contact point - requests without one are liable
# to be blocked outright. See https://musicbrainz.org/doc/MusicBrainz_API
MUSICBRAINZ_USER_AGENT = appinfo.user_agent()


class MusicBrainzBusy(RuntimeError):
    """MusicBrainz refused the request because it is rate limiting or overloaded (429/502/503/504)."""


_musicbrainz_lock = threading.Lock()
_musicbrainz_last_request = 0.0


MUSICBRAINZ_TIMEOUT = 15.0  # seconds; the GUI sets this from the network settings


def configure(timeout: float) -> None:
    """Request timeout in seconds (the GUI passes its network setting)."""
    global MUSICBRAINZ_TIMEOUT
    MUSICBRAINZ_TIMEOUT = float(timeout)


def api_get(path: str, params: dict[str, str], timeout: Optional[float] = None) -> dict:
    """
    GET a MusicBrainz API endpoint. Enforces MusicBrainz's rate limit
    (documented as roughly one request per second) via a module-level
    lock so overlapping calls from different threads still queue up
    properly, rather than each independently waiting and bursting.
    """
    global _musicbrainz_last_request
    with _musicbrainz_lock:
        wait = 1.0 - (time.monotonic() - _musicbrainz_last_request)
        if wait > 0:
            time.sleep(wait)

        query = urllib.parse.urlencode({**params, "fmt": "json"})
        url = f"{MUSICBRAINZ_BASE_URL}/{path}?{query}"
        request = urllib.request.Request(url, headers={"User-Agent": MUSICBRAINZ_USER_AGENT})

        try:
            with urllib.request.urlopen(request, timeout=timeout or MUSICBRAINZ_TIMEOUT) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503, 504):
                raise MusicBrainzBusy(f"MusicBrainz is busy ({exc.code}): {exc.reason}") from exc
            raise Failure("http_error", f"MusicBrainz returned an error ({exc.code}): {exc.reason}",
                          host="MusicBrainz", status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise Failure("unreachable", f"Could not reach MusicBrainz: {exc.reason}", detail=str(exc.reason),
                          host="MusicBrainz") from exc
        finally:
            _musicbrainz_last_request = time.monotonic()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Failure("bad_response", f"MusicBrainz returned unexpected data: {exc}", host="MusicBrainz") from exc


@dataclass
class MusicBrainzCandidate:
    release_id: str
    title: str
    artist: str
    date: str = ""
    track_count: int = 0
    format_hint: str = ""   # e.g. "Blu-ray", "Digital Media" - the release's MusicBrainz format, if any
    score: int = 0          # MusicBrainz's own relevance score (0-100) for this search, not our playlist score
    medium_track_counts: list[int] = field(default_factory=list)  # one entry per disc, in order


_DISC_TAG_RE = re.compile(r"[\s\-_]*[\[(]?\b(?:disc|disk|cd|bd|dvd)[\s\-_]*(\d+)[\])]?\s*$", re.IGNORECASE)


def split_disc_tag(album: str) -> tuple[str, Optional[int]]:
    """'Live Tour 2025 DISC 1' -> ('Live Tour 2025', 1). Search engines choke on the tag."""
    match = _DISC_TAG_RE.search(album)
    if not match or not album[: match.start()].strip():
        return album.strip(), None
    return album[: match.start()].strip(), int(match.group(1))


def pick_medium(track_counts: list[int], chapter_count: Optional[int] = None,
                disc_number: Optional[int] = None) -> int:
    """Index of the medium that best fits this playlist: an explicit disc number wins,
    then the disc whose track count is closest to the chapter count, then the first."""
    if not track_counts:
        return 0
    if disc_number and 1 <= disc_number <= len(track_counts):
        return disc_number - 1
    if chapter_count:
        return min(range(len(track_counts)), key=lambda i: abs(track_counts[i] - chapter_count))
    return 0


def _parse_musicbrainz_release_candidates(data: dict) -> list[MusicBrainzCandidate]:
    """Shared parsing for any MusicBrainz /release search response, regardless of query type."""
    candidates: list[MusicBrainzCandidate] = []
    for r in data.get("releases", []):
        artist_credit = r.get("artist-credit") or []
        artist_name = artist_credit[0].get("name", "") if artist_credit else ""
        media = r.get("media") or []
        counts = [m.get("track-count", 0) or 0 for m in media]
        track_count = sum(counts)
        format_hint = media[0].get("format") or "" if media else ""
        candidates.append(
            MusicBrainzCandidate(
                release_id=r.get("id", ""),
                title=r.get("title", ""),
                artist=artist_name,
                date=r.get("date", ""),
                track_count=track_count,
                format_hint=format_hint,
                score=r.get("score", 0),
                medium_track_counts=counts,
            )
        )
    return candidates


def search_musicbrainz_releases(
    artist: str,
    album_title: str,
    year: Optional[int] = None,
    limit: int = 8,
) -> list[MusicBrainzCandidate]:
    """
    Search MusicBrainz for release candidates matching an artist/album
    (and optionally year). Returns MusicBrainz's own ranked candidates -
    this is a search, not a lookup, so more than one release can come
    back (different editions, live vs studio versions, reissues). Nothing
    is fetched or applied here; metadata_sources.fetch() reads whichever
    candidate the user picks.
    """
    if not artist.strip() and not album_title.strip():
        raise ValueError("Enter an artist or album title to search MusicBrainz.")

    def term(value: str) -> str:
        return value.strip().replace("\\", " ").replace('"', " ")

    # Either field alone is a valid search; the album is matched as words rather
    # than an exact phrase so a slightly different folder name still finds it.
    query_parts = []
    if artist.strip():
        query_parts.append(f'artist:"{term(artist)}"')
    if album_title.strip():
        query_parts.append(f"release:({term(album_title)})")
    if year:
        query_parts.append(f"date:{year}")
    query = " AND ".join(query_parts)

    data = api_get("release", {"query": query, "limit": str(limit)})
    return _parse_musicbrainz_release_candidates(data)


def search_musicbrainz_releases_by_barcode(barcode: str, limit: int = 8) -> list[MusicBrainzCandidate]:
    """
    Search MusicBrainz for release candidates matching a UPC/EAN barcode
    (the number printed under the barcode lines on the disc case/sleeve).
    Unlike an artist/album text search, a barcode identifies one specific
    physical or digital edition - which matters for concert Blu-rays,
    since different regional pressings/reissues of the same show often
    carry different bonus tracks or a different tracklist entirely.

    Whitespace and dashes are stripped, since barcodes are sometimes
    copied with them; everything else is sent to MusicBrainz as-is, so
    a mistyped digit just returns no results rather than a wrong match.
    """
    digits = re.sub(r"[^0-9]", "", barcode)
    if not digits:
        raise ValueError("Enter a barcode (the number under the barcode lines) to search.")

    data = api_get("release", {"query": f"barcode:{digits}", "limit": str(limit)})
    return _parse_musicbrainz_release_candidates(data)
