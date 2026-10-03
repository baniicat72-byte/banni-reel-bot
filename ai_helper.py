import os
import time
import logging
from google import genai
import config

logger = logging.getLogger(__name__)

FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest"
]


def get_genai_client():
    if not config.GEMINI_API_KEY:
        return None
    return genai.Client(api_key=config.GEMINI_API_KEY)


def generate_social_content(user_prompt: str, video_path: str = "") -> dict:
    client = get_genai_client()
    if not client:
        default_caption = f"{user_prompt}\n\n#reels #shorts #tech #viral"
        return {
            "ig_caption": default_caption,
            "fb_caption": default_caption,
            "yt_title": (user_prompt[:85] if user_prompt else "Awesome Tech Reel") + " #Shorts",
            "yt_description": default_caption,
            "yt_tags": ["shorts", "tech", "viral", "reels"],
            "best_time_suggestion": "7:30 PM IST (Evening Peak)"
        }

    uploaded_file = None
    try:
        base_contents = []
        if video_path and os.path.exists(video_path):
            try:
                logger.info(f"Uploading video {video_path} to Gemini...")
                uploaded_file = client.files.upload(file=video_path)
                base_contents.append(uploaded_file)
            except Exception as e:
                logger.warning(f"Video upload failed: {e}")

        prompt = f"""
You are the master social media growth manager for 'BANNI Tech', a viral channel specializing in tech memes, programming, gaming, Linux, and developer culture.
Creator optional notes: "{user_prompt}"

INSTRUCTIONS:
1. Watch the video frames, meme punchline, visual humor, on-screen text, and theme.
2. Write hyper-engaging, viral Hinglish/English content crafted for maximum comments, shares, and watch time.
3. Identify the optimal peak posting time for the Indian audience.

Return your answer EXACTLY using these section markers:
---IG_CAPTION---
(Instagram caption: Attention-grabbing first line hook, witty relatable body, emojis, question to boost comments, and 12-15 trending hashtags including #bannitech #techmemes #codinglife).
---FB_CAPTION---
(Facebook page caption: Engaging story/meme format).
---YT_TITLE---
(YouTube Shorts title: Under 90 chars, high CTR click-magnet, ending with #Shorts).
---YT_DESCRIPTION---
(YouTube description: Short summary + 4-5 relevant hashtags).
---YT_TAGS---
(5-8 comma-separated YouTube tags).
---BEST_TIME---
(Suggested best posting time, e.g. '7:30 PM IST (Evening Peak)')
"""
        base_contents.append(prompt)

        # Try models in fallback order in case of 503 high demand
        text = ""
        for model_name in FALLBACK_MODELS:
            try:
                logger.info(f"Generating content with model {model_name}...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=base_contents
                )
                text = response.text
                if text:
                    break
            except Exception as model_err:
                logger.warning(f"Model {model_name} failed ({model_err}), trying fallback...")
                time.sleep(1)

        if not text:
            raise RuntimeError("All Gemini models failed")

        def extract_section(start_delim, end_delim=None):
            if start_delim not in text:
                return ""
            part = text.split(start_delim, 1)[1]
            if end_delim and end_delim in part:
                part = part.split(end_delim, 1)[0]
            return part.strip()

        ig = extract_section("---IG_CAPTION---", "---FB_CAPTION---")
        fb = extract_section("---FB_CAPTION---", "---YT_TITLE---")
        yt_title = extract_section("---YT_TITLE---", "---YT_DESCRIPTION---")
        yt_desc = extract_section("---YT_DESCRIPTION---", "---YT_TAGS---")
        yt_tags_str = extract_section("---YT_TAGS---", "---BEST_TIME---")
        best_time = extract_section("---BEST_TIME---")

        yt_tags = [t.strip() for t in yt_tags_str.split(",") if t.strip()]

        return {
            "ig_caption": ig or (user_prompt + "\n\n#reels #viral #bannitech"),
            "fb_caption": fb or ig,
            "yt_title": yt_title or ((user_prompt[:85] or "Awesome Tech Reel") + " #Shorts"),
            "yt_description": yt_desc or ig,
            "yt_tags": yt_tags or ["shorts", "tech", "viral", "bannitech"],
            "best_time_suggestion": best_time or "7:30 PM IST"
        }

    except Exception as e:
        logger.error(f"Error in Gemini video generation: {e}")
        fallback = f"{user_prompt}\n\n#reels #shorts #tech #viral"
        return {
            "ig_caption": fallback,
            "fb_caption": fallback,
            "yt_title": (user_prompt[:85] if user_prompt else "New Tech Reel") + " #Shorts",
            "yt_description": fallback,
            "yt_tags": ["shorts", "tech", "viral"],
            "best_time_suggestion": "7:30 PM IST"
        }
    finally:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
