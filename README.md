# 🤖 BANNI Tech - Multi-Platform Social Auto-Poster Bot

A Telegram AI Bot that automatically posts and schedules:
- 📸 **Instagram Reels** (Meta Graph API)
- 🔵 **Facebook Page Reels** (Meta Graph API)
- 🔴 **YouTube Shorts** (YouTube Data API v3)
- 🧠 **AI Caption, Hook & Hashtag Generation** (Google Gemini)

---

## 🚀 Setup Steps (Sirf 1 Baar Karna Hai)

### Step 1: Telegram Bot Token (2 Minutes)
1. Telegram me search karein: `@BotFather`
2. Message bhejein: `/newbot`
3. Apna bot name aur username set karein (e.g., `banni_social_bot`).
4. `@BotFather` aapko ek **Token** dega (jaise `72819281:AAH...`).
5. Is token ko `.env` file me daalein:
   ```env
   TELEGRAM_BOT_TOKEN=72819281:AAH...
   ```

---

### Step 2: Google Gemini API Key (Bilkul Free)
1. Kholein: [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. "Create API Key" par click karein.
3. Key copy karke `.env` me paste karein:
   ```env
   GEMINI_API_KEY=AIzaSy...
   ```

---

### Step 3: Meta (Facebook Page & Instagram) Token
1. Kholein: [https://developers.facebook.com/](https://developers.facebook.com/)
2. "Tools" -> **Graph API Explorer** par jayein.
3. User or Page me apna **Facebook Page (BANNI Tech)** select karein.
4. Permissions add karein:
   - `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`
   - `instagram_basic`, `instagram_content_publish`
5. Generate Token karke Page Access Token copy karein aur `.env` me daalein:
   ```env
   META_ACCESS_TOKEN=EAAG...
   FACEBOOK_PAGE_ID=your_page_id
   INSTAGRAM_ACCOUNT_ID=your_instagram_id
   ```

---

### Step 4: YouTube Shorts Auth (Optional - One Time)
1. [Google Cloud Console](https://console.cloud.google.com/) me jayein -> "YouTube Data API v3" enable karein.
2. "Credentials" -> "Create OAuth client ID" -> Desktop App.
3. Download JSON karke is folder me `client_secrets.json` ke naam se save karein.
4. Terminal me ek baar ye command chalayein:
   ```bash
   ./venv/bin/python setup_youtube_auth.py
   ```
5. Browser me Google account se login karein. Kaam done!

---

## 🏃‍♂️ Bot Ko Start Kaise Karein

Terminal me:
```bash
cd /home/banni/.gemini/antigravity/scratch/social-reel-bot
./run.sh
```

---

## 📱 Mobile Se Daily Kaise Use Karein

1. Phone me Telegram kholein aur apne bot ko message karein.
2. Koi bhi video bhejien (Reel / Short) aur caption/topic likhein.
3. Bot turant AI se tagda caption + title bana kar preview dikhayega.
4. Button dabayein:
   - `🚀 Post to ALL (Insta + FB + YT)` -> Turant teeno jagah upload!
   - `⏰ Schedule Tonight (7:00 PM)` -> Aaj shaam 7 baje ke liye schedule!
