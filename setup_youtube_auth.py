import os
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

def main():
    if not os.path.exists(config.YOUTUBE_CLIENT_SECRETS_FILE):
        print(f"Error: {config.YOUTUBE_CLIENT_SECRETS_FILE} not found!")
        print("Please download client_secrets.json from Google Cloud Console and place it in this folder.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(config.YOUTUBE_CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=8080)

    with open(config.YOUTUBE_TOKEN_FILE, "w") as token:
        token.write(creds.to_json())

    print(f"\nSuccess! YouTube token saved to {config.YOUTUBE_TOKEN_FILE}")
    print("Now your bot can automatically upload YouTube Shorts!")

if __name__ == "__main__":
    main()
