import os
from datetime import datetime, timezone

import mysql.connector
import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()


def get_spotify():
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            scope="user-read-recently-played",
            cache_path=".cache",
        )
    )


def get_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )


def parse_played_at(text):
    """Spotify sends UTC like '2026-10-23T05:05:17.113Z'. MySQL wants a naive UTC datetime."""
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def save_play(cur, item):
    """Save one play and everything it depends on. Returns True if the play was new."""
    track = item["track"]
    if track.get("id") is None:  # local file, nothing to key on
        return False

    album = track["album"]
    images = album.get("images") or []
    cover_url = images[0]["url"] if images else None

    cur.execute(
        "INSERT IGNORE INTO albums "
        "(album_id, name, album_type, release_date, total_tracks, cover_url) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (album["id"], album["name"], album.get("album_type"),
         album.get("release_date"), album.get("total_tracks"), cover_url),
    )

    cur.execute(
        "INSERT IGNORE INTO tracks "
        "(track_id, name, album_id, duration_ms, explicit) "
        "VALUES (%s, %s, %s, %s, %s)",
        (track["id"], track["name"], album["id"],
         track.get("duration_ms"), track.get("explicit")),
    )

    for artist in track["artists"]:
        if artist.get("id") is None:
            continue
        cur.execute(
            "INSERT IGNORE INTO artists (artist_id, name) VALUES (%s, %s)",
            (artist["id"], artist["name"]),
        )
        cur.execute(
            "INSERT IGNORE INTO track_artists (track_id, artist_id) VALUES (%s, %s)",
            (track["id"], artist["id"]),
        )

    context = item.get("context") or {}
    cur.execute(
        "INSERT IGNORE INTO plays "
        "(track_id, played_at, context_type, context_uri) "
        "VALUES (%s, %s, %s, %s)",
        (track["id"], parse_played_at(item["played_at"]),
         context.get("type"), context.get("uri")),
    )
    return cur.rowcount == 1  # 1 = new row, 0 = duplicate ignored


def main():
    sp = get_spotify()
    items = sp.current_user_recently_played(limit=50)["items"]

    conn = get_db()
    cur = conn.cursor()
    new_plays = 0
    try:
        for item in items:
            if save_play(cur, item):
                new_plays += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    print(f"Fetched {len(items)} plays, {new_plays} new, "
          f"{len(items) - new_plays} already stored or skipped")


if __name__ == "__main__":
    main()