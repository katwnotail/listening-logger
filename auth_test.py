from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()  # reads .env into environment variables

sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        scope="user-read-recently-played",
        cache_path=".cache",  # token file, already in .gitignore
    )
)

me = sp.current_user()
print(f"Logged in as: {me['display_name']}")

results = sp.current_user_recently_played(limit=5)
for item in results["items"]:
    track = item["track"]
    artists = ", ".join(a["name"] for a in track["artists"])
    print(f"{item['played_at']}  {artists} - {track['name']}")