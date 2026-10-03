import os
import sys
import html
import time
import threading
import http.server
import socketserver
import logging
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

import config
import ai_helper
import meta_publisher
import youtube_publisher

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Global State ─────────────────────────────────────────────────────────────
USER_STATE: dict[int, dict] = {}

DEFAULT_SETTINGS = {
    "made_for_kids": False,
    "hide_likes": False,
    "allow_comments": True,
    "privacy": "public"
}


def get_user_state(uid: int) -> dict:
    if uid not in USER_STATE:
        USER_STATE[uid] = {
            "settings": dict(DEFAULT_SETTINGS),
            "edit_field": None,  # 'title', 'caption', or None
        }
    return USER_STATE[uid]


def is_authorized(user_id: int) -> bool:
    return (not config.ALLOWED_USER_IDS) or (user_id in config.ALLOWED_USER_IDS)


async def safe_edit_text(message, text: str, reply_markup=None):
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"HTML edit failed ({e}), falling back to plain text")
        clean = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
        try:
            return await message.edit_text(clean, reply_markup=reply_markup, parse_mode=None)
        except Exception as e2:
            logger.error(f"Fallback edit also failed: {e2}")


async def safe_reply_text(message, text: str, reply_markup=None):
    try:
        return await message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"HTML reply failed ({e}), falling back to plain text")
        clean = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
        return await message.reply_text(clean, reply_markup=reply_markup, parse_mode=None)


# ── Structured Target Builder ────────────────────────────────────────────────
def build_all_targets() -> list[dict]:
    """Builds a flat, clean list of all available posting targets."""
    targets = []
    
    # 1. YouTube Shorts
    yt_channels = youtube_publisher.get_all_youtube_channels()
    for ch in yt_channels:
        targets.append({
            "id": ch["id"],
            "name": ch["name"],
            "icon": "🔴",
            "type": "youtube",
            "channel_key": ch["id"]
        })

    # 2. Meta Targets
    pages = meta_publisher.get_all_managed_pages()
    for idx, p in enumerate(pages):
        if p.get("page_id"):
            targets.append({
                "id": f"fb_{idx}",
                "name": f"FB: {p['page_name']}",
                "icon": "🔵",
                "type": "facebook",
                "page_id": p["page_id"],
                "page_name": p["page_name"],
                "token": p["page_token"]
            })
        if p.get("instagram_id"):
            targets.append({
                "id": f"ig_{idx}",
                "name": f"IG: @{p['instagram_username']}",
                "icon": "📸",
                "type": "instagram",
                "ig_id": p["instagram_id"],
                "username": p["instagram_username"],
                "token": p["page_token"]
            })

    return targets


def parse_schedule_time(timing_mode: str, best_time_str: str) -> tuple[int | None, str | None, str]:
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    
    if timing_mode == "now":
        return None, None, "⚡ Post Immediately (Now)"
    
    elif timing_mode == "ai":
        try:
            t_str = best_time_str.split(" IST")[0].split("(")[0].strip()
            target = datetime.strptime(t_str, "%I:%M %p").replace(
                year=now.year, month=now.month, day=now.day, tzinfo=tz
            )
            if target <= now:
                target += timedelta(days=1)
        except Exception:
            target = now.replace(hour=19, minute=30, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
        ts = int(target.timestamp())
        iso = target.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        label = f"⏰ AI Peak: {target.strftime('%I:%M %p, %d %b')} IST"
        return ts, iso, label

    elif timing_mode == "tonight":
        target = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        ts = int(target.timestamp())
        iso = target.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        label = f"🌙 Tonight: {target.strftime('%I:%M %p, %d %b')} IST"
        return ts, iso, label

    elif timing_mode == "usa_peak":
        target = now.replace(hour=6, minute=30, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        ts = int(target.timestamp())
        iso = target.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        label = f"🇺🇸 USA Peak: {target.strftime('%I:%M %p, %d %b')} IST"
        return ts, iso, label

    return None, None, "⚡ Post Immediately (Now)"


# ── Dashboard & Menus ────────────────────────────────────────────────────────
def build_dashboard_text(st: dict) -> str:
    c = st.get("content", {})
    s = st.get("settings", DEFAULT_SETTINGS)
    timing_label = st.get("timing_label", "⚡ Post Immediately (Now)")
    targets = st.get("all_targets", [])
    selected_ids = st.get("selected_target_ids", set())

    kids_str = "YES" if s["made_for_kids"] else "NO"
    likes_str = "Hidden" if s["hide_likes"] else "Visible"
    comm_str = "ON" if s["allow_comments"] else "OFF"

    target_lines = []
    for t in targets:
        if t["id"] in selected_ids:
            target_lines.append(f"• {t['icon']} {t['name']}")

    if not target_lines:
        targets_display = "⚠️ <i>Koi platform select nahi hai! 'Choose Platforms' me jaakar select karein.</i>"
    else:
        targets_display = "\n".join(target_lines)

    title_display = c.get("yt_title", "Untitled")
    caption_display = c.get("ig_caption", "No caption")
    if len(caption_display) > 260:
        caption_display = caption_display[:260] + "..."

    meta_errs = meta_publisher.get_meta_token_errors()
    err_banner = f"\n⚠️ <b>Token Alert:</b> <i>{html.escape(meta_errs[0])}</i>\n" if meta_errs else ""

    return (
        "🎬 <b>VIDEO CONTROL DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>Title (YouTube):</b>\n<code>{html.escape(title_display)}</code>\n\n"
        f"💬 <b>Caption (FB/IG):</b>\n{html.escape(caption_display)}\n\n"
        f"⏰ <b>Timing:</b> <code>{html.escape(timing_label)}</code>\n"
        f"⚙️ <b>Settings:</b> Kids: <code>{kids_str}</code> | Likes: <code>{likes_str}</code> | Comments: <code>{comm_str}</code>\n\n"
        f"🎯 <b>Selected Platforms ({len(target_lines)} of {len(targets)}):</b>\n{targets_display}\n"
        f"{err_banner}"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 Customize karein ya Confirm karke Publish karein:"
    )


def dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 CONFIRM & PUBLISH NOW", callback_data="act:publish")],
        [
            InlineKeyboardButton("✍️ Edit Title / Caption", callback_data="act:edit_menu"),
            InlineKeyboardButton("⏰ Change Timing",      callback_data="act:timing_menu"),
        ],
        [
            InlineKeyboardButton("🎯 Choose Platforms",    callback_data="act:platforms_menu"),
            InlineKeyboardButton("⚙️ Video Settings",      callback_data="act:settings_menu"),
        ],
        [
            InlineKeyboardButton("🔄 Re-run AI",           callback_data="act:regen"),
            InlineKeyboardButton("❌ Cancel",               callback_data="act:cancel"),
        ]
    ])


def edit_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Edit YouTube Title", callback_data="edit:title")],
        [InlineKeyboardButton("💬 Edit Instagram / FB Caption", callback_data="edit:caption")],
        [InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="act:dashboard")],
    ])


def timing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Post Immediately (Now)", callback_data="time:now")],
        [InlineKeyboardButton("⏰ AI Best Peak Time",       callback_data="time:ai")],
        [InlineKeyboardButton("🌙 Tonight 8:00 PM IST",     callback_data="time:tonight")],
        [InlineKeyboardButton("🇺🇸 USA Peak (6:30 AM IST)",  callback_data="time:usa_peak")],
        [InlineKeyboardButton("⬅️ Back to Dashboard",       callback_data="act:dashboard")],
    ])


def platforms_keyboard(targets: list, selected_ids: set) -> InlineKeyboardMarkup:
    rows = []
    # Display 2 buttons per row for compact clean UI
    temp_row = []
    for t in targets:
        tick = "✅" if t["id"] in selected_ids else "❌"
        btn = InlineKeyboardButton(f"{tick} {t['icon']} {t['name']}", callback_data=f"tog:{t['id']}")
        temp_row.append(btn)
        if len(temp_row) == 2:
            rows.append(temp_row)
            temp_row = []
    if temp_row:
        rows.append(temp_row)

    rows.append([
        InlineKeyboardButton("✅ Select ALL", callback_data="tog:all_on"),
        InlineKeyboardButton("❌ Clear ALL",  callback_data="tog:all_off")
    ])
    rows.append([InlineKeyboardButton("⬅️ Done / Back to Dashboard", callback_data="act:dashboard")])
    return InlineKeyboardMarkup(rows)


def settings_keyboard(s: dict) -> InlineKeyboardMarkup:
    kids = "✅ YES" if s["made_for_kids"] else "❌ NO"
    likes = "🔒 Hidden" if s["hide_likes"] else "👁️ Visible"
    comm = "✅ ON" if s["allow_comments"] else "❌ OFF"
    priv = s["privacy"].upper()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👶 Made for Kids : {kids}", callback_data="stg:kids")],
        [InlineKeyboardButton(f"❤️ Like Count   : {likes}", callback_data="stg:likes")],
        [InlineKeyboardButton(f"💬 Comments     : {comm}",  callback_data="stg:comments")],
        [InlineKeyboardButton(f"🔐 Privacy      : {priv}",  callback_data="stg:privacy")],
        [InlineKeyboardButton("⬅️ Done / Back to Dashboard", callback_data="act:dashboard")],
    ])


# ── Clean Error Formatter ────────────────────────────────────────────────────
def clean_error_message(err_str: str) -> str:
    if "pages_manage_posts" in err_str:
        return "Facebook Page par posting permission missing hai (pages_manage_posts add karein)"
    if "instagram_content_publish" in err_str:
        return "Instagram Reels permission missing hai (instagram_content_publish add karein)"
    if "Session has expired" in err_str or "Error validating access token" in err_str:
        return "Meta Session Expire ho gaya hai (Naya token generate karein)"
    return err_str[:120]


# ── Handlers ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        return await update.message.reply_text("⛔ Unauthorized.")

    targets = build_all_targets()
    lines = [f"• {t['icon']} {t['name']}" for t in targets]

    text = (
        "👋 <b>BANNI Tech AI Auto-Poster Bot</b> 🤖\n\n"
        f"<b>Active Connected Targets ({len(targets)}):</b>\n" +
        ("\n".join(lines) if lines else "❌ Koi accounts connected nahi hain") +
        "\n\n📹 <b>Koi bhi video bhejein</b> — AI analyze karega aur aapke saamne <b>Full Interactive Dashboard</b> open hoga jahan aap Title, Caption, Schedule Time aur Platforms sab khud control kar sakenge!"
    )
    await safe_reply_text(update.message, text)


async def handle_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_authorized(uid):
        return

    msg = update.message
    vobj = msg.video or msg.document
    if not vobj:
        return

    prompt = msg.caption or ""
    wait = await msg.reply_text("👁️ <i>Gemini AI video analyze kar raha hai...</i>", parse_mode="HTML")

    fobj = await ctx.bot.get_file(vobj.file_id)
    ext = os.path.splitext(getattr(vobj, "file_name", "v.mp4") or "v.mp4")[1] or ".mp4"
    fname = f"vid_{uid}_{int(datetime.now().timestamp())}{ext}"
    fpath = str(config.TEMP_DIR / fname)
    await fobj.download_to_drive(fpath)

    content = ai_helper.generate_social_content(prompt, fpath)
    all_targets = build_all_targets()
    
    # Default: Select ALL targets
    selected_ids = {t["id"] for t in all_targets}

    st = get_user_state(uid)
    st.update({
        "video_path": fpath,
        "content": content,
        "all_targets": all_targets,
        "selected_target_ids": selected_ids,
        "prompt": prompt,
        "timing_mode": "now",
        "timing_label": "⚡ Post Immediately (Now)",
        "sched_timestamp": None,
        "sched_iso": None,
        "edit_field": None,
    })

    dash_text = build_dashboard_text(st)
    await safe_edit_text(wait, dash_text, reply_markup=dashboard_keyboard())


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    st = get_user_state(uid)
    field = st.get("edit_field")

    if not field:
        return

    text = update.message.text.strip()
    c = st.setdefault("content", {})

    if field == "title":
        c["yt_title"] = text
        st["edit_field"] = None
        await update.message.reply_text("✅ <b>YouTube Title Update Ho Gaya!</b>", parse_mode="HTML")
    elif field == "caption":
        c["ig_caption"] = text
        c["fb_caption"] = text
        st["edit_field"] = None
        await update.message.reply_text("✅ <b>Instagram & Facebook Caption Update Ho Gaya!</b>", parse_mode="HTML")

    dash_text = build_dashboard_text(st)
    await safe_reply_text(update.message, dash_text, reply_markup=dashboard_keyboard())


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    st = get_user_state(uid)

    # ── Dashboard View ──
    if data == "act:dashboard":
        st["edit_field"] = None
        dash_text = build_dashboard_text(st)
        return await safe_edit_text(query.message, dash_text, reply_markup=dashboard_keyboard())

    # ── Edit Menu ──
    if data == "act:edit_menu":
        return await safe_edit_text(
            query.message,
            "✍️ <b>Aapko kya edit karna hai?</b>",
            reply_markup=edit_menu_keyboard()
        )

    if data == "edit:title":
        st["edit_field"] = "title"
        return await safe_edit_text(
            query.message,
            "📝 <b>Naya YouTube Title bhejein:</b>\n\nNeeche message box me apna naya title type karke send karein!"
        )

    if data == "edit:caption":
        st["edit_field"] = "caption"
        return await safe_edit_text(
            query.message,
            "💬 <b>Naya Instagram / FB Caption bhejein:</b>\n\nNeeche message box me apna caption aur hashtags type karke send karein!"
        )

    # ── Timing Menu ──
    if data == "act:timing_menu":
        return await safe_edit_text(
            query.message,
            "⏰ <b>Schedule Time Chunein:</b>",
            reply_markup=timing_keyboard()
        )

    if data.startswith("time:"):
        mode = data.split(":", 1)[1]
        best_t = st.get("content", {}).get("best_time_suggestion", "7:30 PM IST")
        ts, iso, label = parse_schedule_time(mode, best_t)
        st["timing_mode"] = mode
        st["timing_label"] = label
        st["sched_timestamp"] = ts
        st["sched_iso"] = iso
        dash_text = build_dashboard_text(st)
        return await safe_edit_text(query.message, dash_text, reply_markup=dashboard_keyboard())

    # ── Platforms Menu ──
    if data == "act:platforms_menu":
        targets = st.get("all_targets", [])
        selected = st.get("selected_target_ids", set())
        meta_errs = meta_publisher.get_meta_token_errors()
        err_msg = "\n\n⚠️ <i>Meta Token Expired: FB/IG pages load nahi hue. Naya token update karein.</i>" if meta_errs else ""
        return await safe_edit_text(
            query.message,
            f"🎯 <b>Platforms Toggle Karein ({len(selected)} of {len(targets)} Selected):</b>{err_msg}",
            reply_markup=platforms_keyboard(targets, selected)
        )

    if data.startswith("tog:"):
        action = data.split(":", 1)[1]
        targets = st.get("all_targets", [])
        selected = st.setdefault("selected_target_ids", set())

        if action == "all_on":
            selected.update(t["id"] for t in targets)
        elif action == "all_off":
            selected.clear()
        else:
            if action in selected:
                selected.remove(action)
            else:
                selected.add(action)

        try:
            return await safe_edit_text(
                query.message,
                f"🎯 <b>Platforms Toggle Karein ({len(selected)} of {len(targets)} Selected):</b>",
                reply_markup=platforms_keyboard(targets, selected)
            )
        except Exception:
            pass

    # ── Settings Menu ──
    if data == "act:settings_menu":
        s = st.get("settings", DEFAULT_SETTINGS)
        return await safe_edit_text(
            query.message,
            "⚙️ <b>Video Settings:</b>",
            reply_markup=settings_keyboard(s)
        )

    if data.startswith("stg:"):
        s = st.setdefault("settings", dict(DEFAULT_SETTINGS))
        key = data[4:]
        if key == "kids":
            s["made_for_kids"] = not s["made_for_kids"]
        elif key == "likes":
            s["hide_likes"] = not s["hide_likes"]
        elif key == "comments":
            s["allow_comments"] = not s["allow_comments"]
        elif key == "privacy":
            cycle = ["public", "private", "unlisted"]
            s["privacy"] = cycle[(cycle.index(s["privacy"]) + 1) % len(cycle)]
        try:
            return await query.edit_message_reply_markup(reply_markup=settings_keyboard(s))
        except Exception:
            pass

    # ── Regenerate AI ──
    if data == "act:regen":
        vp = st.get("video_path")
        if not vp or not os.path.exists(vp):
            return await safe_edit_text(query.message, "⚠️ Video file expired, please resend.")
        await safe_edit_text(query.message, "🔄 <b>Gemini AI naya viral content bana raha hai...</b>")
        st["content"] = ai_helper.generate_social_content(st.get("prompt", ""), vp)
        dash_text = build_dashboard_text(st)
        return await safe_edit_text(query.message, dash_text, reply_markup=dashboard_keyboard())

    # ── Cancel ──
    if data == "act:cancel":
        vp = st.get("video_path")
        if vp and os.path.exists(vp):
            try: os.remove(vp)
            except: pass
        USER_STATE.pop(uid, None)
        return await safe_edit_text(query.message, "❌ Cancelled. Video deleted.")

    # ── PUBLISH EXECUTION ──
    if data == "act:publish":
        vpath = st.get("video_path")
        if not vpath or not os.path.exists(vpath):
            return await safe_edit_text(query.message, "⚠️ Session expired. Please send the video again.")

        all_targets = st.get("all_targets", [])
        selected_ids = st.get("selected_target_ids", set())

        active_targets = [t for t in all_targets if t["id"] in selected_ids]
        if not active_targets:
            return await query.answer("⚠️ Koi platform select nahi hai! 'Choose Platforms' me jaakar select karein.", show_alert=True)

        content = st.get("content", {})
        s = st.get("settings", DEFAULT_SETTINGS)
        sched_ts = st.get("sched_timestamp")
        sched_iso = st.get("sched_iso")

        await safe_edit_text(query.message, f"🚀 <b>Uploading to {len(active_targets)} Selected Platforms...</b>")
        results = []

        for t in active_targets:
            # 1. YouTube Shorts
            if t["type"] == "youtube":
                ch_key = t.get("channel_key", "yt_1")
                r = youtube_publisher.upload_youtube_short(
                    vpath,
                    content.get("yt_title", "Shorts"),
                    content.get("yt_description", ""),
                    content.get("yt_tags", []),
                    sched_iso,
                    made_for_kids=s["made_for_kids"],
                    channel_key=ch_key
                )
                if r.get("success"):
                    status = "Scheduled" if sched_iso else "Published"
                    results.append(f"• 🔴 <b>{t['name']}:</b> ✅ {status} (→ <a href='{r.get('url')}'>Watch Short</a>)")
                else:
                    results.append(f"• 🔴 <b>{t['name']}:</b> ❌ {clean_error_message(r.get('error', 'Failed'))}")

            # 2. Facebook Page
            elif t["type"] == "facebook":
                r = meta_publisher.publish_facebook_reel(
                    t["page_id"], t["token"],
                    vpath, content.get("fb_caption", ""), sched_ts
                )
                if r.get("success"):
                    status = "Scheduled" if sched_ts else "Published"
                    results.append(f"• 🔵 <b>{t['name']}:</b> ✅ {status}")
                else:
                    results.append(f"• 🔵 <b>{t['name']}:</b> ❌ {clean_error_message(r.get('error', 'Failed'))}")

            # 3. Instagram Account
            elif t["type"] == "instagram":
                r = meta_publisher.publish_instagram_reel(
                    t["ig_id"], t["token"],
                    vpath, content.get("ig_caption", "")
                )
                if r.get("success"):
                    results.append(f"• 📸 <b>{t['name']}:</b> ✅ Published (Reel Live!)")
                else:
                    results.append(f"• 📸 <b>{t['name']}:</b> ❌ {clean_error_message(r.get('error', 'Failed'))}")

        # Cleanup video file
        if os.path.exists(vpath):
            try: os.remove(vpath)
            except: pass

        report = (
            f"📊 <b>Publishing Report ({len(active_targets)} Platforms):</b>\n\n" +
            "\n".join(results) +
            "\n\n━━━━━━━━━━━━━━━━━━━━━━\nDone! Next video bhej sakte hain."
        )
        await safe_reply_text(query.message, report)


# ── Health server for Render / Cloud deployment ──────────────────────────────
class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"BANNI Tech Reel Bot is Running!")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("0.0.0.0", port), HealthHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        logger.info(f"Health check server running on 0.0.0.0:{port} (Render ready)")
    except Exception as e:
        logger.warning(f"Could not start health server: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    if not config.TELEGRAM_BOT_TOKEN or "1234567890" in config.TELEGRAM_BOT_TOKEN:
        print("❌ Add real TELEGRAM_BOT_TOKEN in .env")
        sys.exit(1)

    start_health_server()

    while True:
        try:
            app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
            app.add_handler(CommandHandler(["start", "help"], cmd_start))
            app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
            app.add_handler(CallbackQueryHandler(handle_callback))

            print("🤖 Pro Bot with Bulletproof Target Mapping is LIVE!")
            app.run_polling()
            break
        except Exception as e:
            logger.warning(f"Connection dropped ({e}), auto-reconnecting in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    main()
