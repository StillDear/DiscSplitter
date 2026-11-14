"""
metadata_sources.py

Album metadata from public online catalogues that need no account or API key:

  - musicbrainz : MusicBrainz release data + front cover from the Cover Art Archive
  - itunes      : Apple Music / iTunes Search API (artwork up to 1000 px, genre, date)
  - deezer      : Deezer public API (artwork, genres, per-track artists)
  - discogs     : Discogs database (strong on live / boutique / regional pressings);
                  works without an account, an optional personal token adds
                  search thumbnails and a higher rate limit

Every source returns the same shapes so the GUI does not care where data came from:

  search(...) -> list[Candidate]
  fetch(source, id) -> AlbumInfo
  download_cover(url, cache_dir, key) -> Path

Only what the user typed (artist / album / barcode) is sent to these services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import extractor
from core import musicbrainz

SOURCES = ("musicbrainz", "itunes", "deezer", "discogs")
USER_AGENT = musicbrainz.MUSICBRAINZ_USER_AGENT
COVER_SIZES = ("standard", "large", "original")
_config = {"timeout": 15.0, "country": "US", "cover_size": "large", "discogs_token": ""}


def configure(proxy_mode: str = "system", proxy_url: str = "", timeout: float = 15.0,
              country: str = "US", cover_size: str = "large", discogs_token: str = "") -> None:
    """Apply network settings to every request this process makes (MusicBrainz included).

    proxy_mode: "system" (Windows Internet settings / *_PROXY variables), "none", or "custom".
    """
    if proxy_mode == "none":
        handler = urllib.request.ProxyHandler({})
    elif proxy_mode == "custom" and proxy_url:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    else:
        handler = urllib.request.ProxyHandler()  # reads the system proxy now
    urllib.request.install_opener(urllib.request.build_opener(handler))
    _config.update(timeout=float(timeout), country=(country or "US").upper(),
                   cover_size=cover_size if cover_size in COVER_SIZES else "large",
                   discogs_token=(discogs_token or "").strip())
    musicbrainz.configure(timeout)


def _mb(fn, *args):
    """MusicBrainz answers 503 when requests come too fast; wait and retry once."""
    try:
        return fn(*args)
    except RuntimeError as exc:
        if "(503)" not in str(exc):
            raise
        time.sleep(2)
        return fn(*args)


@dataclass
class Candidate:
    source: str
    id: str
    title: str
    artist: str
    date: str = ""
    track_count: int = 0
    detail: str = ""
    thumb: str = ""          # small artwork URL for the result list (may 404 for MusicBrainz)


@dataclass
class TrackInfo:
    title: str
    artist: str = ""
    seconds: float | None = None


@dataclass
class AlbumInfo:
    source: str
    album: str = ""
    artist: str = ""
    album_artist: str = ""
    date: str = ""
    genre: str = ""
    cover_url: str = ""
    tracks: list[TrackInfo] = field(default_factory=list)


def _get_json(url: str, headers: dict | None = None) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=_config["timeout"]) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{urllib.parse.urlsplit(url).netloc} returned an error ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{urllib.parse.urlsplit(url).netloc} returned unexpected data") from exc


def _credit(credits) -> str:
    """MusicBrainz artist-credit list -> display string ("A feat. B")."""
    return "".join((c.get("name") or (c.get("artist") or {}).get("name", "")) + (c.get("joinphrase") or "")
                   for c in credits or []).strip()


# ---------------------------------------------------------------- search

def search(source: str, artist: str = "", album: str = "", barcode: str = "") -> list[Candidate]:
    artist, album, barcode = artist.strip(), album.strip(), barcode.strip()
    if source == "musicbrainz":
        found = (_mb(extractor.search_musicbrainz_releases_by_barcode, barcode) if barcode
                 else _mb(extractor.search_musicbrainz_releases, artist, album))
        return [Candidate("musicbrainz", c.release_id, c.title, c.artist, c.date, c.track_count,
                          " · ".join(x for x in (c.format_hint, c.date) if x),
                          f"https://coverartarchive.org/release/{c.release_id}/front-250") for c in found]
    term = " ".join(x for x in (artist, album) if x) or barcode
    if not term:
        return []
    if source == "itunes":
        params = {"term": term, "entity": "album", "media": "music", "limit": "12", "country": _config["country"]}
        if barcode and not (artist or album):
            params = {"upc": barcode, "entity": "album", "country": _config["country"]}
            data = _get_json("https://itunes.apple.com/lookup?" + urllib.parse.urlencode(params))
        else:
            data = _get_json("https://itunes.apple.com/search?" + urllib.parse.urlencode(params))
        return [Candidate("itunes", str(r["collectionId"]), r.get("collectionName", ""), r.get("artistName", ""),
                          (r.get("releaseDate") or "")[:10], int(r.get("trackCount") or 0),
                          " · ".join(x for x in (r.get("primaryGenreName", ""), (r.get("releaseDate") or "")[:4]) if x),
                          r.get("artworkUrl100", ""))
                for r in data.get("results", []) if r.get("wrapperType") == "collection" and r.get("collectionId")]
    if source == "deezer":
        data = _get_json("https://api.deezer.com/search/album?" + urllib.parse.urlencode({"q": term, "limit": 12}))
        if not data.get("data") and int(data.get("total") or 0) > 0:
            # Deezer reports matches but withholds them outside the countries it serves.
            raise RuntimeError("REGION_BLOCKED:deezer")
        return [Candidate("deezer", str(r["id"]), r.get("title", ""), (r.get("artist") or {}).get("name", ""), "",
                          int(r.get("nb_tracks") or 0), r.get("record_type", ""), r.get("cover_medium", ""))
                for r in data.get("data", []) if r.get("id")]
    if source == "discogs":
        params = {"type": "release", "per_page": "12"}
        if barcode:
            params["barcode"] = barcode
        else:
            params.update({k: v for k, v in (("artist", artist), ("release_title", album)) if v})
        data = _discogs("/database/search?" + urllib.parse.urlencode(params))
        out = []
        for r in data.get("results", []):
            artist_name, _, title = (r.get("title") or "").partition(" - ")
            if not title:
                artist_name, title = "", artist_name
            out.append(Candidate("discogs", str(r["id"]), title.strip(), _discogs_name(artist_name.strip()),
                                 str(r.get("year") or ""), 0,
                                 " \u00b7 ".join(x for x in (", ".join((r.get("format") or [])[:2]), r.get("country", ""),
                                                             str(r.get("year") or "")) if x),
                                 r.get("thumb", "")))
        return out
    raise ValueError(f"Unknown metadata source: {source}")


# ---------------------------------------------------------------- Discogs helpers


_DISCOGS_SUFFIX = re.compile(r"\s\(\d+\)$")   # "Kana Nishino (2)" disambiguation numbers


def _discogs(path: str) -> dict:
    headers = {"Authorization": f"Discogs token={_config['discogs_token']}"} if _config["discogs_token"] else {}
    return _get_json("https://api.discogs.com" + path, headers)


def _discogs_name(name: str) -> str:
    return _DISCOGS_SUFFIX.sub("", name or "").strip()


def _discogs_artists(artists) -> str:
    text = ""
    for a in artists or []:
        text += _discogs_name(a.get("anv") or a.get("name", ""))
        join = (a.get("join") or "").strip()
        if join:
            text += join + " " if join == "," else f" {join} "
    return text.strip()


def _discogs_seconds(value: str) -> float | None:
    parts = [p for p in (value or "").strip().split(":") if p.isdigit()]
    if not parts:
        return None
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + int(p)
    return float(seconds) or None


def _discogs_tracks(items, album_artist: str) -> list[TrackInfo]:
    tracks: list[TrackInfo] = []
    for t in items or []:
        kind = t.get("type_", "track")
        if kind == "index" and t.get("sub_tracks"):
            tracks.extend(_discogs_tracks(t["sub_tracks"], album_artist))
        elif kind == "track":
            tracks.append(TrackInfo(t.get("title", ""), _discogs_artists(t.get("artists")) or album_artist,
                                    _discogs_seconds(t.get("duration", ""))))
    return tracks


# ---------------------------------------------------------------- fetch

def fetch(source: str, item_id: str) -> AlbumInfo:
    if source == "musicbrainz":
        data = _mb(musicbrainz.api_get, f"release/{item_id}", {"inc": "recordings+artist-credits+genres+tags+release-groups"})
        artist = _credit(data.get("artist-credit"))
        genres = data.get("genres") or []
        group_id = (data.get("release-group") or {}).get("id")
        if not genres and group_id:
            # Genres are usually voted on the release group, not on each edition.
            group = _mb(musicbrainz.api_get, f"release-group/{group_id}", {"inc": "genres+tags"})
            genres = group.get("genres") or group.get("tags") or []
        genres = sorted(genres or data.get("tags") or [], key=lambda g: -int(g.get("count") or 0))
        tracks = [TrackInfo(t.get("title") or (t.get("recording") or {}).get("title", ""),
                            _credit(t.get("artist-credit")) or artist,
                            (t.get("length") or 0) / 1000 or None)
                  for medium in data.get("media") or [] for t in medium.get("tracks") or []]
        return AlbumInfo("musicbrainz", data.get("title", ""), artist, artist, data.get("date", ""),
                         ", ".join(g["name"].title() for g in genres[:2] if g.get("name")),
                         f"https://coverartarchive.org/release/{item_id}/"
                         + {"standard": "front-500", "large": "front-1200", "original": "front"}[_config["cover_size"]], tracks)
    if source == "itunes":
        data = _get_json("https://itunes.apple.com/lookup?" + urllib.parse.urlencode(
            {"id": item_id, "entity": "song", "country": _config["country"]}))
        rows = data.get("results", [])
        album = next((r for r in rows if r.get("wrapperType") == "collection"), {})
        songs = sorted((r for r in rows if r.get("wrapperType") == "track"),
                       key=lambda r: (r.get("discNumber") or 1, r.get("trackNumber") or 0))
        art = album.get("artworkUrl100", "")
        return AlbumInfo("itunes", album.get("collectionName", ""), album.get("artistName", ""), album.get("artistName", ""),
                         (album.get("releaseDate") or "")[:10], album.get("primaryGenreName", ""),
                         art.replace("100x100bb", {"standard": "600x600bb", "large": "1200x1200bb",
                                                   "original": "3000x3000bb"}[_config["cover_size"]]) if art else "",
                         [TrackInfo(s.get("trackName", ""), s.get("artistName", ""), (s.get("trackTimeMillis") or 0) / 1000 or None)
                          for s in songs])
    if source == "deezer":
        data = _get_json(f"https://api.deezer.com/album/{urllib.parse.quote(item_id)}")
        if "error" in data:
            raise RuntimeError(f"Deezer: {data['error'].get('message', 'not found')}")
        artist = (data.get("artist") or {}).get("name", "")
        return AlbumInfo("deezer", data.get("title", ""), artist, artist, data.get("release_date", ""),
                         ", ".join(g.get("name", "") for g in ((data.get("genres") or {}).get("data") or [])[:2]),
                         data.get("cover_big" if _config["cover_size"] == "standard" else "cover_xl", ""),
                         [TrackInfo(t.get("title", ""), (t.get("artist") or {}).get("name", "") or artist, t.get("duration"))
                          for t in ((data.get("tracks") or {}).get("data") or [])])
    if source == "discogs":
        data = _discogs(f"/releases/{urllib.parse.quote(item_id)}")
        artist = _discogs_artists(data.get("artists"))
        images = data.get("images") or []
        cover = next((i for i in images if i.get("type") == "primary"), images[0] if images else {})
        released = (data.get("released") or str(data.get("year") or "")).replace("-00", "")
        tags = data.get("styles") or data.get("genres") or []
        return AlbumInfo("discogs", data.get("title", ""), artist, artist, released, ", ".join(tags[:2]),
                         cover.get("uri", ""), _discogs_tracks(data.get("tracklist"), artist))
    raise ValueError(f"Unknown metadata source: {source}")


# ---------------------------------------------------------------- cover

def _image_suffix(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    return None


def download_cover(url: str, cache_dir: Path, key: str) -> Path:
    """Download artwork into cache_dir; only JPEG/PNG are kept (that is what MKV players read)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_config["timeout"]) as response:
            data = response.read(40 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("No cover art is available for this release." if exc.code == 404
                           else f"Cover download failed ({exc.code})") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not download the cover: {exc.reason}") from exc
    suffix = _image_suffix(data[:8])
    if suffix is None:
        raise RuntimeError("The cover is not a JPEG or PNG image.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + suffix)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------- connection check

CHECK_URLS = {
    "musicbrainz": "https://musicbrainz.org/ws/2/release?query=release%3Atest&limit=1&fmt=json",
    "itunes": "https://itunes.apple.com/search?term=test&entity=album&limit=1",
    "deezer": "https://api.deezer.com/search/album?q=test&limit=1",
    "discogs": "https://api.discogs.com/database/search?q=test&type=release&per_page=1",
}


def check(source: str) -> tuple[str, int, str]:
    """Reach one source with the current network settings -> (state, milliseconds, detail).

    state is "ok", "blocked" (reachable but no data in this region) or "error".
    """
    start = time.monotonic()
    try:
        if source == "musicbrainz":
            data = _mb(_get_json, CHECK_URLS[source])
        elif source == "discogs":
            data = _discogs(CHECK_URLS[source].removeprefix("https://api.discogs.com"))
        else:
            data = _get_json(CHECK_URLS[source])
    except RuntimeError as exc:
        return "error", int((time.monotonic() - start) * 1000), str(exc)
    ms = int((time.monotonic() - start) * 1000)
    if source == "deezer" and not data.get("data") and int(data.get("total") or 0) > 0:
        return "blocked", ms, ""
    return "ok", ms, ""
