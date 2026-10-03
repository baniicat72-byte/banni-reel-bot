import os, time, logging, requests
import config

logger = logging.getLogger(__name__)
BASE_URL = "https://graph.facebook.com/v20.0"


META_ERRORS = []
_PAGE_CACHE = None
_PAGE_CACHE_TIME = 0

def get_meta_token_errors() -> list[str]:
    return list(set(META_ERRORS))


def get_all_managed_pages(force_refresh: bool = False) -> list:
    """
    Fetches ALL Facebook pages + linked Instagram accounts
    PLUS standalone Business Instagram accounts from all configured tokens.
    Cached for 120 seconds to prevent slow bot responses.
    """
    global META_ERRORS, _PAGE_CACHE, _PAGE_CACHE_TIME
    now = time.time()
    if not force_refresh and _PAGE_CACHE is not None and (now - _PAGE_CACHE_TIME) < 120:
        return _PAGE_CACHE

    META_ERRORS.clear()
    items = []
    seen_fb_ids = set()
    seen_ig_ids = set()

    for token in config.META_ACCESS_TOKENS:
        # 1. Fetch Facebook Pages and linked Instagram accounts
        try:
            res = requests.get(
                f"{BASE_URL}/me/accounts",
                params={
                    "fields": "id,name,access_token,instagram_business_account{id,username}",
                    "access_token": token
                },
                timeout=10
            )
            data = res.json()
            if "error" in data:
                err_msg = data["error"].get("message", "")
                if data["error"].get("code") == 190 or "expired" in err_msg.lower():
                    META_ERRORS.append("Meta Token expired (Session ended). Please update META_ACCESS_TOKEN.")
                else:
                    META_ERRORS.append(f"Meta Error: {err_msg[:60]}")
                continue
            for item in data.get("data", []):
                pid = item["id"]
                if pid in seen_fb_ids:
                    continue
                seen_fb_ids.add(pid)

                ig = item.get("instagram_business_account") or {}
                ig_id = ig.get("id")
                ig_user = ig.get("username")
                if ig_id:
                    seen_ig_ids.add(ig_id)

                items.append({
                    "type": "page",
                    "page_id": pid,
                    "page_name": item["name"],
                    "page_token": item.get("access_token", token),
                    "instagram_id": ig_id,
                    "instagram_username": ig_user,
                })
        except Exception as e:
            logger.error(f"Error fetching pages for a token: {e}")

        # 2. Fetch Business Portfolios & their direct Instagram Business Accounts
        try:
            biz_res = requests.get(
                f"{BASE_URL}/me/businesses",
                params={"access_token": token, "fields": "id,name"},
                timeout=10
            ).json()
            for biz in biz_res.get("data", []):
                biz_id = biz["id"]
                ig_res = requests.get(
                    f"{BASE_URL}/{biz_id}/instagram_business_accounts",
                    params={"access_token": token, "fields": "id,username,name"},
                    timeout=10
                ).json()
                for ig in ig_res.get("data", []):
                    ig_id = ig["id"]
                    if ig_id in seen_ig_ids:
                        continue
                    seen_ig_ids.add(ig_id)
                    items.append({
                        "type": "standalone_ig",
                        "page_id": None,
                        "page_name": None,
                        "page_token": token,
                        "instagram_id": ig_id,
                        "instagram_username": ig.get("username"),
                    })
        except Exception as e:
            logger.error(f"Error fetching business IG accounts: {e}")

    _PAGE_CACHE = items
    _PAGE_CACHE_TIME = now
    return items


def _do_publish_fb_reel(page_id, page_token, video_path, description, scheduled_timestamp=None):
    headers = {"Authorization": f"Bearer {page_token}"}
    try:
        init_url = f"{BASE_URL}/{page_id}/video_reels"
        init = requests.post(init_url, headers=headers, json={"upload_phase": "start"}).json()
        if "video_id" not in init:
            return {"success": False, "error": f"Init failed: {init}"}

        vid_id = init["video_id"]
        upload_url = init["upload_url"]
        fsize = os.path.getsize(video_path)

        with open(video_path, "rb") as f:
            r = requests.post(upload_url, data=f, headers={
                "Authorization": f"OAuth {page_token}",
                "offset": "0",
                "file_size": str(fsize),
                "Content-Type": "application/octet-stream"
            })
            if r.status_code not in (200, 201):
                return {"success": False, "error": f"Upload failed: {r.text}"}

        payload = {"upload_phase": "finish", "video_id": vid_id, "description": description}
        if scheduled_timestamp:
            payload["video_state"] = "SCHEDULED"
            payload["scheduled_publish_time"] = scheduled_timestamp
        else:
            payload["video_state"] = "PUBLISHED"

        finish = requests.post(init_url, headers=headers, json=payload).json()
        if finish.get("success"):
            return {"success": True, "video_id": vid_id}
        return {"success": False, "error": str(finish)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def publish_facebook_reel(page_id, page_token, video_path, description, scheduled_timestamp=None):
    tokens_to_try = [page_token] + [t for t in config.META_ACCESS_TOKENS if t != page_token]
    last_err = ""
    for tok in tokens_to_try:
        res = _do_publish_fb_reel(page_id, tok, video_path, description, scheduled_timestamp)
        if res.get("success"):
            return res
        last_err = res.get("error", "")
    return {"success": False, "error": last_err}


def _do_publish_ig_reel(ig_user_id, access_token, video_path, caption):
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        fsize = os.path.getsize(video_path)
        init = requests.post(f"{BASE_URL}/{ig_user_id}/media", headers=headers, json={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption
        }).json()

        if "uri" not in init or "id" not in init:
            return {"success": False, "error": f"IG init failed: {init}"}

        cid = init["id"]
        with open(video_path, "rb") as f:
            r = requests.post(init["uri"], data=f, headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(fsize),
                "Content-Type": "application/octet-stream"
            })
            if r.status_code not in (200, 201):
                return {"success": False, "error": f"Upload failed: {r.text}"}

        for _ in range(30):
            time.sleep(3)
            sc = requests.get(f"{BASE_URL}/{cid}", headers=headers,
                              params={"fields": "status_code"}).json().get("status_code")
            if sc == "FINISHED":
                break
            if sc == "ERROR":
                return {"success": False, "error": "IG processing failed"}

        pub = requests.post(f"{BASE_URL}/{ig_user_id}/media_publish",
                            headers=headers, json={"creation_id": cid}).json()
        if "id" in pub:
            return {"success": True, "media_id": pub["id"]}
        return {"success": False, "error": str(pub)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def publish_instagram_reel(ig_user_id, access_token, video_path, caption):
    tokens_to_try = [access_token] + [t for t in config.META_ACCESS_TOKENS if t != access_token]
    last_err = ""
    for tok in tokens_to_try:
        res = _do_publish_ig_reel(ig_user_id, tok, video_path, caption)
        if res.get("success"):
            return res
        last_err = res.get("error", "")
        logger.warning(f"IG upload attempt with token failed ({last_err}), trying next token...")
    return {"success": False, "error": last_err}
