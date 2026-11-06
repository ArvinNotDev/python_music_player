"""Initial canonical track, album, and artist schema."""

MIGRATION = """
CREATE TABLE artists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE
);
CREATE TABLE albums (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    album_artist TEXT NOT NULL DEFAULT '',
    year INTEGER,
    artwork_path TEXT,
    UNIQUE(title COLLATE NOCASE, album_artist COLLATE NOCASE)
);
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    artist_id INTEGER REFERENCES artists(id) ON DELETE SET NULL,
    album_id INTEGER REFERENCES albums(id) ON DELETE SET NULL,
    album_artist TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK(duration_ms >= 0),
    track_number INTEGER CHECK(track_number IS NULL OR track_number > 0),
    disc_number INTEGER CHECK(disc_number IS NULL OR disc_number > 0),
    year INTEGER CHECK(year IS NULL OR year > 0),
    genre TEXT NOT NULL DEFAULT '',
    composer TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    bitrate INTEGER CHECK(bitrate IS NULL OR bitrate > 0),
    sample_rate INTEGER CHECK(sample_rate IS NULL OR sample_rate > 0),
    artwork_path TEXT,
    date_added TEXT NOT NULL,
    last_played TEXT,
    play_count INTEGER NOT NULL DEFAULT 0 CHECK(play_count >= 0),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK(is_available IN (0, 1)),
    bpm REAL CHECK(bpm IS NULL OR bpm >= 0)
);
CREATE INDEX idx_tracks_title ON tracks(title COLLATE NOCASE);
CREATE INDEX idx_tracks_artist_id ON tracks(artist_id);
CREATE INDEX idx_tracks_album_id ON tracks(album_id);
CREATE INDEX idx_tracks_date_added ON tracks(date_added DESC);
CREATE INDEX idx_tracks_last_played ON tracks(last_played DESC);
"""
