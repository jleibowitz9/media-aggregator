"""Media Aggregator — Daily digest of design & tech content."""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.yaml"


def get_lookback_hours() -> int:
    """Return 72 on Monday (to capture the weekend), 24 otherwise."""
    today = datetime.now(timezone.utc).weekday()  # 0 = Monday
    return 72 if today == 0 else 24

# Ensure imports work whether run as `python src/main.py` or `python -m src.main`
sys.path.insert(0, str(ROOT_DIR))


def load_config() -> dict:
    """Load and return the YAML config."""
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Media Aggregator digest")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Write email to preview.html instead of sending",
    )
    args = parser.parse_args()

    config = load_config()
    print(f"Loaded config with {len(config.get('bluesky', {}).get('accounts', []))} Bluesky accounts")
    print(f"  and {len(config.get('rss', {}).get('feeds', []))} RSS feeds")

    lookback_hours = get_lookback_hours()
    print(f"Lookback window: {lookback_hours}h ({'Monday — includes weekend' if lookback_hours == 72 else 'standard weekday'})")

    # Phase 2: Bluesky
    bluesky_posts = []
    try:
        from src.bluesky import fetch_bluesky
        bluesky_posts = fetch_bluesky(config.get("bluesky", {}), lookback_hours=lookback_hours)
        print(f"Fetched {len(bluesky_posts)} Bluesky posts")
    except ImportError:
        print("Bluesky fetcher not yet implemented, skipping...")

    # Phase 3: RSS
    rss_posts = []
    try:
        from src.rss import fetch_rss
        rss_posts = fetch_rss(config.get("rss", {}), lookback_hours=lookback_hours)
        print(f"Fetched {len(rss_posts)} RSS posts")
    except ImportError:
        print("RSS fetcher not yet implemented, skipping...")

    # Phase 4: Format and send/preview
    try:
        from src.formatter import format_digest
        from src.send import send_digest, preview_digest

        digest_data = format_digest(
            bluesky_posts=bluesky_posts,
            rss_posts=rss_posts,
            config=config.get("email", {}),
        )

        if args.preview:
            preview_digest(digest_data)
        else:
            to_email = os.environ.get("TO_EMAIL")
            if not to_email:
                print("Error: TO_EMAIL environment variable required for sending")
                sys.exit(1)
            send_digest(digest_data, to_email=to_email)
    except ImportError:
        print("Formatter/sender not yet implemented, skipping...")
        if bluesky_posts or rss_posts:
            print("\n--- Raw results ---")
            for post in bluesky_posts[:5]:
                print(f"  [Bluesky] @{post['author']}: {post['text'][:80]}...")
            for post in rss_posts[:5]:
                print(f"  [RSS] {post['source']}: {post['title']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
