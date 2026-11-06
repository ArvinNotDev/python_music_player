"""Library sources, playlists, playback history, and settings."""

MIGRATION = """
ALTER TABLE tracks ADD COLUMN file_size INTEGER;
ALTER TABLE tracks ADD COLUMN file_mtime_ns INTEGER;
CREATE TABLE library_folders (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    date_added TEXT NOT NULL,
    last_scanned TEXT
);
CREATE TABLE playlists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK(is_favorite IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_playlist_single_favorites ON playlists(is_favorite) WHERE is_favorite = 1;
CREATE TABLE playlist_tracks (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id INTEGER REFERENCES tracks(id) ON DELETE SET NULL,
    source_path TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(playlist_id, position)
);
CREATE UNIQUE INDEX idx_playlist_unique_tracks ON playlist_tracks(playlist_id, track_id)
    WHERE track_id IS NOT NULL;
CREATE INDEX idx_playlist_track_path ON playlist_tracks(playlist_id, source_path);
CREATE TABLE favorites (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL
);
CREATE TABLE playback_history (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    played_at TEXT NOT NULL
);
CREATE INDEX idx_history_played_at ON playback_history(played_at DESC);
CREATE INDEX idx_history_track_id ON playback_history(track_id);
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""
