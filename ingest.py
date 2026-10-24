import logging
import os
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import mysql.connector
import requests
import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

log = logging.getLogger("ingest")


class AuthError(Exception):
    """The cached Spotify login is missing or can't be refreshed."""


def setup_logging():
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(
        LOG_DIR / "ingest.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    log.addHandler(file_handler)
    if sys.stderr is not None:  # pythonw.exe has no console
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        log.addHandler(console)

def is_transient(exc):
    """Errors worth retrying: network trouble and temporary server errors."""
    if isinstance(exc, (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):
        return True
    if isinstance(exc, spotipy.SpotifyException):
        return exc.http_status in (429, 500, 502, 503, 504)
    if isinstance(exc, (mysql.connector.errors.InterfaceError,
                        mysql.connector.errors.OperationalError)):
        return True
    return False


def with_retries(func, what, attempts=3, base_delay=5):
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            if not is_transient(exc) or attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("%s failed (%s: %s); retrying in %ds (%d/%d)",
                        what, type(exc).__name__, exc, delay, attempt, attempts - 1)
            time.sleep(delay)


def get_spotify():
    auth = SpotifyOAuth(
        scope="user-read-recently-played",
        cache_path=str(BASE_DIR / ".cache"),
        open_browser=False,  # never wait for a human during an unattended run
    )
    try:
        cached = auth.cache_handler.get_cached_token()
        token = auth.validate_token(cached) if cached else None  # refreshes if expired
    except Exception as exc:
        raise AuthError(f"Token refresh failed: {exc}") from exc
    if token is None:
        raise AuthError("No valid Spotify token in cache. "
                        "Run auth_test.py interactively to log in again.")
    return spotipy.Spotify(auth_manager=auth)


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


def run():
    sp = get_spotify()
    items = with_retries(
        lambda: sp.current_user_recently_played(limit=50)["items"],
        "Spotify fetch",
    )

    conn = with_retries(get_db, "MySQL connect")
    cur = conn.cursor()
    new_plays = 0
    try:
        for item in items:
            if save_play(cur, item):
                new_plays += 1
        conn.commit()
    except Exception:
        conn.rollback()  # all-or-nothing: next run re-fetches and retries safely
        raise
    finally:
        cur.close()
        conn.close()

    log.info("Fetched %d plays, %d new, %d already stored or skipped",
             len(items), new_plays, len(items) - new_plays)
    if len(items) == 50 and new_plays == 50:
        log.warning("All 50 fetched plays were new. If this isn't the first run, "
                    "plays may have been missed; run the logger more often.")


def main():
    setup_logging()
    log.info("Run started")
    try:
        run()
    except AuthError as exc:
        log.error("Authentication problem: %s", exc)
        return 1
    except Exception:
        log.exception("Run failed")
        return 1
    log.info("Run finished OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())