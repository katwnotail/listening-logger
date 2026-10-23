CREATE DATABASE IF NOT EXISTS listening
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE listening;

CREATE TABLE IF NOT EXISTS artists (
  artist_id VARCHAR(32) PRIMARY KEY,
  name      VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS albums (
  album_id     VARCHAR(32) PRIMARY KEY,
  name         VARCHAR(500) NOT NULL,
  album_type   VARCHAR(20),
  release_date VARCHAR(10),    -- raw text: "2024", "2024-05" or "2024-05-17"
  total_tracks INT,
  cover_url    VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS tracks (
  track_id    VARCHAR(32) PRIMARY KEY,
  name        VARCHAR(500) NOT NULL,
  album_id    VARCHAR(32),
  duration_ms INT,
  explicit    BOOLEAN,
  FOREIGN KEY (album_id) REFERENCES albums(album_id)
);

CREATE TABLE IF NOT EXISTS track_artists (
  track_id  VARCHAR(32),
  artist_id VARCHAR(32),
  PRIMARY KEY (track_id, artist_id),
  FOREIGN KEY (track_id)  REFERENCES tracks(track_id),
  FOREIGN KEY (artist_id) REFERENCES artists(artist_id)
);

CREATE TABLE IF NOT EXISTS plays (
  play_id      INT AUTO_INCREMENT PRIMARY KEY,
  track_id     VARCHAR(32) NOT NULL,
  played_at    DATETIME(3) NOT NULL,   -- stored in UTC
  context_type VARCHAR(20),            -- playlist/album/artist, can be NULL
  context_uri  VARCHAR(100),
  UNIQUE KEY uniq_play (played_at, track_id),
  FOREIGN KEY (track_id) REFERENCES tracks(track_id)
);