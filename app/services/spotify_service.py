from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from app.models.track import Track


SPOTIFY_ACCOUNTS_URL = "https://accounts.spotify.com"
SPOTIFY_API_URL = "https://api.spotify.com/v1"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"
DEFAULT_CHART_PLAYLIST_ID = "37i9dQZEVXbMDoHDwVN2tF"
SCOPES = ("user-library-read", "playlist-read-private", "playlist-read-collaborative")
CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{32}$")


class SpotifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpotifyPlaylist:
    id: str
    name: str
    owner: str
    total_tracks: int

    @property
    def label(self) -> str:
        suffix = f" ({self.total_tracks})" if self.total_tracks else ""
        return f"{self.name}{suffix}"


class SpotifyService:
    """Small Spotify Web API client using Authorization Code with PKCE."""

    def __init__(self, storage_dir: Path | None = None):
        self._storage_dir = storage_dir or Path.home() / ".zzvuk"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._token_path = self._storage_dir / "spotify_token.json"
        self._config_path = self._storage_dir / "spotify_config.json"
        self._token = self._load_json(self._token_path)
        self._config = self._load_json(self._config_path)

    def is_configured(self) -> bool:
        return bool(self.client_id())

    def is_authorized(self) -> bool:
        return bool(self._token.get("access_token") and self._token.get("refresh_token"))

    def client_id(self) -> str:
        return str(self._config.get("client_id") or os.environ.get("SPOTIFY_CLIENT_ID") or "").strip()

    def redirect_uri(self) -> str:
        return str(self._config.get("redirect_uri") or DEFAULT_REDIRECT_URI).strip()

    def set_client(self, client_id: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> None:
        clean_client_id = client_id.strip()
        clean_redirect_uri = redirect_uri.strip() or DEFAULT_REDIRECT_URI
        if not clean_client_id:
            raise SpotifyError("Spotify Client ID is required.")
        if not CLIENT_ID_PATTERN.fullmatch(clean_client_id):
            raise SpotifyError(
                "Spotify Client ID must be the 32-character value from Spotify Dashboard, not Client Secret or app name."
            )
        self._config = {"client_id": clean_client_id, "redirect_uri": clean_redirect_uri}
        self._save_json(self._config_path, self._config)

    def logout(self) -> None:
        self._token = {}
        if self._token_path.exists():
            self._token_path.unlink()

    def authorize(self, timeout_seconds: int = 180) -> None:
        client_id = self.client_id()
        if not client_id:
            raise SpotifyError("Set Spotify Client ID first.")

        redirect_uri = self.redirect_uri()
        parsed = urlparse(redirect_uri)
        if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.scheme != "http":
            raise SpotifyError("Redirect URI must be a local http URL, for example http://127.0.0.1:8765/callback.")

        verifier = self._code_verifier()
        challenge = self._code_challenge(verifier)
        state = secrets.token_urlsafe(24)
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }

        result = self._wait_for_callback(parsed, lambda: webbrowser.open(
            f"{SPOTIFY_ACCOUNTS_URL}/authorize?{urlencode(params)}"
        ), timeout_seconds)
        if result.get("state") != state:
            raise SpotifyError("Spotify authorization state mismatch.")
        code = result.get("code")
        if not code:
            raise SpotifyError(result.get("error") or "Spotify authorization did not return a code.")

        payload = self._post_form(
            f"{SPOTIFY_ACCOUNTS_URL}/api/token",
            {
                "client_id": client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": verifier,
            },
        )
        self._store_token(payload)

    def current_user_saved_tracks(self, limit: int = 50) -> list[Track]:
        payload = self._get("/me/tracks", {"limit": max(1, min(limit, 50))})
        return self._tracks_from_paged_items(payload, nested_key="track")

    def search_tracks(self, query: str, limit: int = 30) -> list[Track]:
        if not query.strip():
            return []
        payload = self._get(
            "/search",
            {
                "q": query.strip(),
                "type": "track",
                "limit": max(1, min(limit, 50)),
            },
        )
        tracks = payload.get("tracks", {}).get("items", [])
        return [track for raw in tracks if (track := self._track_from_payload(raw)) is not None]

    def chart_tracks(self, limit: int = 50) -> list[Track]:
        playlist_id = str(self._config.get("chart_playlist_id") or DEFAULT_CHART_PLAYLIST_ID)
        return self.playlist_tracks(playlist_id, limit=limit)

    def current_user_playlists(self, limit: int = 50) -> list[SpotifyPlaylist]:
        payload = self._get("/me/playlists", {"limit": max(1, min(limit, 50))})
        playlists = []
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            playlist_id = item.get("id")
            name = item.get("name")
            if not playlist_id or not name:
                continue
            owner = item.get("owner") or {}
            tracks = item.get("tracks") or {}
            playlists.append(
                SpotifyPlaylist(
                    id=str(playlist_id),
                    name=str(name),
                    owner=str(owner.get("display_name") or owner.get("id") or "Spotify"),
                    total_tracks=int(tracks.get("total") or 0),
                )
            )
        return playlists

    def playlist_tracks(self, playlist_id: str, limit: int = 50) -> list[Track]:
        payload = self._get(
            f"/playlists/{playlist_id}/tracks",
            {
                "limit": max(1, min(limit, 100)),
                "fields": "items(track(id,name,artists(name),album(name,images),duration_ms,preview_url,external_urls,uri,is_playable,restrictions)),next,total",
            },
        )
        return self._tracks_from_paged_items(payload, nested_key="track")

    def _get(self, path: str, params: dict | None = None) -> dict:
        token = self._access_token()
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{SPOTIFY_API_URL}{path}{query}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return self._open_json(request)

    def _access_token(self) -> str:
        if not self.is_authorized():
            raise SpotifyError("Authorize Spotify first.")
        expires_at = float(self._token.get("expires_at") or 0)
        if expires_at - 30 <= time.time():
            self._refresh_access_token()
        token = self._token.get("access_token")
        if not token:
            raise SpotifyError("Spotify access token is missing.")
        return str(token)

    def _refresh_access_token(self) -> None:
        refresh_token = self._token.get("refresh_token")
        if not refresh_token:
            raise SpotifyError("Spotify refresh token is missing.")
        payload = self._post_form(
            f"{SPOTIFY_ACCOUNTS_URL}/api/token",
            {
                "client_id": self.client_id(),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if "refresh_token" not in payload:
            payload["refresh_token"] = refresh_token
        self._store_token(payload)

    def _post_form(self, url: str, form: dict) -> dict:
        request = Request(
            url,
            data=urlencode(form).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._open_json(request)

    def _open_json(self, request: Request) -> dict:
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            retry_after = exc.headers.get("Retry-After")
            if retry_after:
                raise SpotifyError(f"Spotify rate limit reached. Retry after {retry_after} seconds.") from exc
            message = self._spotify_error_message(detail)
            if "invalid_client" in detail:
                raise SpotifyError(
                    "Spotify rejected the Client ID. Copy the 32-character Client ID from Spotify Dashboard > Settings, not Client Secret."
                ) from exc
            if message:
                raise SpotifyError(f"Spotify API error {exc.code}: {message}") from exc
            raise SpotifyError(f"Spotify API error {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise SpotifyError(f"Spotify network error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SpotifyError("Spotify returned an invalid JSON response.") from exc

    @staticmethod
    def _spotify_error_message(detail: str) -> str:
        try:
            payload = json.loads(detail)
        except json.JSONDecodeError:
            return detail
        if not isinstance(payload, dict):
            return detail
        error = payload.get("error")
        description = payload.get("error_description")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if description:
            return f"{error}: {description}" if error else str(description)
        return str(error or "")

    def _store_token(self, payload: dict) -> None:
        expires_in = int(payload.get("expires_in") or 3600)
        self._token = {
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),
            "token_type": payload.get("token_type", "Bearer"),
            "expires_at": time.time() + expires_in,
            "scope": payload.get("scope", " ".join(SCOPES)),
        }
        self._save_json(self._token_path, self._token, private=True)

    def _tracks_from_paged_items(self, payload: dict, nested_key: str) -> list[Track]:
        tracks = []
        for item in payload.get("items", []):
            raw_track = item.get(nested_key) if isinstance(item, dict) else None
            if raw_track is None and nested_key == "track":
                raw_track = item
            track = self._track_from_payload(raw_track)
            if track is not None:
                tracks.append(track)
        return tracks

    def _track_from_payload(self, payload: object) -> Track | None:
        if not isinstance(payload, dict) or payload.get("type", "track") != "track":
            return None
        track_id = payload.get("id")
        title = payload.get("name")
        if not track_id or not title:
            return None

        artists = payload.get("artists") or []
        artist_names = [
            str(artist.get("name"))
            for artist in artists
            if isinstance(artist, dict) and artist.get("name")
        ]
        album = payload.get("album") or {}
        restrictions = payload.get("restrictions") or {}
        genre = "Spotify"
        if payload.get("is_playable") is False:
            genre = "Spotify unavailable"
        elif restrictions:
            genre = f"Spotify restricted: {restrictions.get('reason', 'market')}"
        elif not payload.get("preview_url"):
            genre = "Spotify preview unavailable"

        external_urls = payload.get("external_urls") or {}
        return Track(
            path=Path(f"spotify:track:{track_id}"),
            title=str(title),
            artist=", ".join(artist_names) or "Unknown Artist",
            album=str(album.get("name") or "Spotify"),
            genre=genre,
            duration_seconds=float(payload.get("duration_ms") or 0) / 1000.0,
            stream_url=payload.get("preview_url") or None,
            external_url=external_urls.get("spotify") or None,
            source="spotify",
        )

    @staticmethod
    def _code_verifier() -> str:
        return secrets.token_urlsafe(64)[:96]

    @staticmethod
    def _code_challenge(verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @staticmethod
    def _wait_for_callback(parsed_redirect, open_browser, timeout_seconds: int) -> dict:
        result = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed_path = urlparse(self.path)
                if parsed_path.path != parsed_redirect.path:
                    self.send_response(404)
                    self.end_headers()
                    return
                values = parse_qs(parsed_path.query)
                result.update({key: values[key][0] for key in values if values[key]})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h3>Spotify authorization complete.</h3>You can return to ZZvuk.</body></html>"
                )

            def log_message(self, _format, *_args):
                return

        server = HTTPServer((parsed_redirect.hostname, parsed_redirect.port or 80), CallbackHandler)
        server.timeout = timeout_seconds
        open_browser()
        server.handle_request()
        server.server_close()
        if not result:
            raise SpotifyError("Spotify authorization timed out.")
        return result

    @staticmethod
    def _load_json(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _save_json(path: Path, payload: dict, private: bool = False) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if private:
            try:
                path.chmod(0o600)
            except OSError:
                pass
