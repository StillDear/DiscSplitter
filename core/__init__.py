"""
The disc-to-songs engine, without any GUI. Layers (a module imports only from layers below it):

    0  appinfo, models, jobs,       name and version, data, progress/cancellation,
       tools                        running external tools
    1  manifest, chapter_marks,     job checkpoint, reading and editing chapters,
       tagging, naming,             tags and covers, output names,
       bluray_iso, dvd              disc images and DVD titles
    2  sources, tracklist,          scanning sources, track names from files and aligning them,
       musicbrainz, split,          cutting files, disk space, checking results
       space, verify
    3  setlist, preview,            pasted set lists, audition clips and loudness outlines,
       metadata_sources,            album data from online catalogues,
       webpage, ocr                 set lists from web pages and screenshots
    4  pipeline                     the whole export in one call
"""
