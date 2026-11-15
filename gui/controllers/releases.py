"""Finding the release in an online catalogue and laying its tracklist over the chapters."""
from __future__ import annotations

from PySide6.QtCore import Slot

from core import metadata_sources, musicbrainz
from .. import logic


class ReleaseSearch:
    """The part of NamesController that searches the catalogues (MusicBrainz, Apple Music, Deezer, Discogs)."""

    def refresh_release_fits(self):
        """Releases compare their track count with the chapters still being named."""
        chapters = self.naming_count()
        for i, row in enumerate(self.release_model.rows):
            self.release_model.change(i, chapters=chapters, fit=logic.track_fit(row['tracks'], chapters))

    def start_over(self, artist, album):
        """A new source: forget the releases found for the last one. Returns the album name to search for."""
        album, self.disc_number = musicbrainz.split_disc_tag(album)
        self.candidates = []
        self.release_model.replace([])
        self.put(mb='idle', mbError='', mbRelease='', mbArtist=artist, mbAlbum=album)
        return album

    def release_fit(self, candidate):
        """Track count of the disc that would be used, and how well it fits the chapter count."""
        counts = candidate.disc_track_counts or ([candidate.track_count] if candidate.track_count else [])
        if not counts:
            return 0, 'unknown'
        tracks = counts[musicbrainz.pick_medium(counts, self.naming_count(), self.disc_number)]
        return tracks, logic.track_fit(tracks, self.naming_count())

    @Slot(str, str, str)
    def search(self, artist, album, barcode):
        """Look for the release in the chosen catalogue; the best fits by track count come first."""
        if self.working:
            return
        self.put(mbArtist=artist, mbAlbum=album)
        if not (artist.strip() or album.strip() or barcode.strip()):
            self.put(mb='error', mbError=self.tr('mbNeedQuery'))
            return
        source = self.state['titleSource']

        def done(found):
            fits = {id(c): self.release_fit(c) for c in found}
            found = sorted(found, key=lambda c: (logic.FIT_ORDER[fits[id(c)][1]], -c.score))
            self.candidates = found
            self.release_model.replace([dict(
                label=f'{c.artist} — {c.title}' if c.artist else c.title,
                detail=' · '.join(x for x in (c.detail, self.tr('mbDiscs').format(n=len(c.disc_track_counts))
                                                   if len(c.disc_track_counts) > 1 else '') if x),
                tracks=fits[id(c)][0], chapters=self.naming_count(), fit=fits[id(c)][1], chosen=False,
                thumb=c.thumb if source != 'musicbrainz' else '') for c in found])
            self.put(mb='results' if found else 'empty', mbError='')
            # Preview the best fit straight away; nothing is applied until the user confirms.
            if found and fits[id(found[0])][1] == 'exact':
                self.selectRelease(0)

        def failed(exc):
            self.put(mb='error', mbError=self.app.metadata.source_error(exc))
        self.task(lambda p: metadata_sources.search(source, artist, album, barcode), done, failed,
                  begin=dict(mb='searching', mbError=''), blocking=False)

    @Slot(int)
    def selectRelease(self, row):
        """Fetch one release's tracklist and lay it over the chapters for review."""
        if self.working or not 0 <= row < len(self.candidates):
            return
        candidate = self.candidates[row]
        for i in range(len(self.release_model.rows)):
            self.release_model.change(i, chosen=i == row)
        chapters, disc = self.naming_count(), self.disc_number
        label = self.release_model.rows[row]['label']

        def work(p):
            info = metadata_sources.fetch(candidate.source, candidate.id, tracks_only=True)
            return metadata_sources.tracklist_entries(info.disc_tracks(chapters, disc))

        def done(entries):
            self.put(mb='results')
            if not entries:
                self.show_waiting_rows()
                self.put(mbRelease='', reviewChecked=0, mb='error', mbError=self.tr('mbNoTracks'))
                return
            self.review_online(label, entries)

        def failed(exc):
            self.put(mb='error', mbError=self.app.metadata.source_error(exc))
        self.task(work, done, failed, begin=dict(mb='loading', mbError=''), blocking=False)

    @Slot(str)
    def setTitleSource(self, source):
        if source not in metadata_sources.SOURCES or self.working or source == self.state['titleSource']:
            return
        self.candidates = []
        self.release_model.replace([])
        self.put(titleSource=source, mb='idle', mbError='')
