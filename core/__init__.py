"""
The disc-to-songs engine, without any GUI. Layers (a module imports only from layers below it):

    0  models, jobs, tools          data, progress/cancellation, running external tools
    1  manifest, chapter_marks,     job checkpoint, reading and editing chapters,
       naming, bluray_iso, dvd      output names, disc images and DVD titles
    2  sources, tracklist,          scanning sources, track names from text and online,
       musicbrainz, split,          cutting files, disk space, checking results
       space, verify
    3  pipeline                     the whole export in one call
"""
