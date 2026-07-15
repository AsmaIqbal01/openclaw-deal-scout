import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    credentials_path = os.environ.get("GMAIL_CREDENTIALS_PATH")
    if not credentials_path:
        print("GMAIL_CREDENTIALS_PATH is not set", file=sys.stderr)
        sys.exit(1)

    token_path = os.path.join(
        os.path.dirname(os.path.abspath(credentials_path)), "token.json"
    )

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())

    print(f"Authorization complete. Token saved to {token_path}")


if __name__ == "__main__":
    main()
