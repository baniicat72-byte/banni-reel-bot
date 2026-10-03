import os
import sys
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

def main():
    channel_num = sys.argv[1] if len(sys.argv) > 1 else "2"
    target_token_file = config.BASE_DIR / f"youtube_token_{channel_num}.json" if channel_num != "1" else config.BASE_DIR / "youtube_token.json"

    if not os.path.exists(config.YOUTUBE_CLIENT_SECRETS_FILE):
        print(f"❌ Error: {config.YOUTUBE_CLIENT_SECRETS_FILE} not found!")
        return

    print(f"🎬 Starting YouTube OAuth Flow for Channel #{channel_num}...")
    print(f"📁 Target token file: {target_token_file}")
    print("=" * 60)

    flow = InstalledAppFlow.from_client_secrets_file(
        config.YOUTUBE_CLIENT_SECRETS_FILE,
        SCOPES
    )

    port = 8080 + int(channel_num) if channel_num.isdigit() else 8082
    creds = flow.run_local_server(
        port=port,
        prompt="consent",
        access_type="offline"
    )

    token_json_str = creds.to_json()
    with open(target_token_file, "w") as f:
        f.write(token_json_str)

    print("=" * 60)
    print(f"✅ Success! YouTube Channel #{channel_num} token saved to:\n{target_token_file}")
    print("\n📋 Token JSON for Render Environment Variables (YOUTUBE_TOKEN_2_JSON):")
    print(token_json_str)
    print("=" * 60)

if __name__ == "__main__":
    main()
