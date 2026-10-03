import os
import logging
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import config

logger = logging.getLogger(__name__)


def get_youtube_service():
    """
    Loads saved OAuth credentials and returns an authorized YouTube API client.
    """
    token_file = config.YOUTUBE_TOKEN_FILE
    if not os.path.exists(token_file):
        logger.warning(f"YouTube token file not found at {token_file}")
        return None

    try:
        creds = Credentials.from_authorized_user_file(token_file, [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube"
        ])
        return build("youtube", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Failed to load YouTube credentials: {e}")
        return None


def upload_youtube_short(video_path: str, title: str, description: str, tags: list = None, publish_at_iso: str = None, made_for_kids: bool = False) -> dict:
    """
    Uploads a YouTube Short.
    If publish_at_iso is given (e.g., '2026-10-02T18:00:00Z'), it schedules the Short.
    """
    youtube = get_youtube_service()
    if not youtube:
        return {"success": False, "error": "YouTube is not authenticated. Run setup_youtube_auth.py first."}

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
