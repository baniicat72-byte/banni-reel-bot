import os
import logging
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import config

logger = logging.getLogger(__name__)


def get_youtube_service(channel_key: str = "yt_1"):
    """
    Loads saved OAuth credentials for a specific channel key (yt_1, yt_2, yt_3)
    and returns an authorized YouTube API client.
    """
    num = channel_key.replace("yt_", "").replace("yt", "")
    if num == "1" or not num:
        token_file = config.BASE_DIR / "youtube_token.json"
        env_var = "YOUTUBE_TOKEN_JSON"
    else:
        token_file = config.BASE_DIR / f"youtube_token_{num}.json"
        env_var = f"YOUTUBE_TOKEN_{num}_JSON"

    if not os.path.exists(token_file):
        yt_json = os.environ.get(env_var)
        if yt_json:
            try:
                with open(token_file, "w") as f:
                    f.write(yt_json)
                logger.info(f"Restored {channel_key} token from env var to {token_file}")
            except Exception as e:
                logger.warning(f"Could not write {token_file}: {e}")
        else:
            return None

    try:
        creds = Credentials.from_authorized_user_file(str(token_file), [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube"
        ])
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to load YouTube credentials for {channel_key}: {e}")
        return None


_CHANNEL_TITLES = {}

def get_channel_title(service, key: str = "") -> str | None:
    num = key.replace("yt_", "").replace("yt", "")
    env_name = os.environ.get(f"YT_NAME_{num}") or os.environ.get(f"YOUTUBE_NAME_{num}")
    if env_name:
        return env_name

    if key and key in _CHANNEL_TITLES:
        return _CHANNEL_TITLES[key]
    try:
        res = service.channels().list(mine=True, part="snippet").execute()
        items = res.get("items", [])
        if items:
            t = items[0]["snippet"]["title"]
            if key:
                _CHANNEL_TITLES[key] = t
            return t
    except Exception:
        pass
    if key:
        _CHANNEL_TITLES[key] = None
    return None


def get_all_youtube_channels() -> list[dict]:
    """Returns a list of all authenticated YouTube channels."""
    channels = []
    # Check yt_1 through yt_9
    for i in range(1, 10):
        key = f"yt_{i}"
        service = get_youtube_service(key)
        if service:
            title = get_channel_title(service, key)
            display_name = f"YT: {title}" if title else f"YouTube Channel {i}"
            channels.append({
                "id": key,
                "name": display_name,
                "service": service
            })
    return channels


def upload_youtube_short(video_path: str, title: str, description: str, tags: list = None, publish_at_iso: str = None, made_for_kids: bool = False, channel_key: str = "yt_1") -> dict:
    """
    Uploads a YouTube Short to a specific channel.
    If publish_at_iso is given (e.g., '2026-10-02T18:00:00Z'), it schedules the Short.
    """
    youtube = get_youtube_service(channel_key)
    if not youtube:
        return {"success": False, "error": f"YouTube ({channel_key}) is not authenticated."}

    try:
        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags or ["shorts", "viral", "tech"],
                "categoryId": "28"  # Science & Technology
            },
            "status": {
                "selfDeclaredMadeForKids": made_for_kids
            }
        }

        if publish_at_iso:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = publish_at_iso
        else:
            body["status"]["privacyStatus"] = "public"

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 5  # 5MB chunks
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"YouTube Upload progress: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        return {
            "success": True,
            "video_id": video_id,
            "url": f"https://youtube.com/shorts/{video_id}",
            "scheduled": bool(publish_at_iso)
        }

    except Exception as e:
        logger.error(f"Error uploading to YouTube: {e}")
        return {"success": False, "error": str(e)}
