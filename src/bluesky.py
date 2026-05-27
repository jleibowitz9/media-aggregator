"""Fetch recent posts from Bluesky via the AT Protocol public API.

Account feeds work without auth. Topic search requires a Bluesky session.
Set BSKY_HANDLE and BSKY_APP_PASSWORD env vars to enable topic search.
"""

import os
import re
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

BASE_URL = "https://public.api.bsky.app/xrpc"
AUTH_URL = "https://bsky.social/xrpc"
DEFAULT_LOOKBACK_HOURS = 24

# Compiled at module load for performance
_skip_patterns_compiled: Optional[list] = None


def _compile_skip_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile skip patterns into case-insensitive regexes."""
    return [re.compile(re.escape(p), re.IGNORECASE) for p in patterns]


def _should_skip(text: str, patterns: list[re.Pattern]) -> bool:
    """Check if a post matches any skip pattern (noise filter)."""
    for pattern in patterns:
        if pattern.search(text):
            return True
    return False


def _post_url(handle: str, rkey: str) -> str:
    """Build a bsky.app URL for a post."""
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse an AT Protocol timestamp (ISO 8601) to UTC datetime."""
    try:
        # Handle both 'Z' suffix and '+00:00'
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _is_recent(ts_str: str, hours: int = DEFAULT_LOOKBACK_HOURS) -> bool:
    """Check if a timestamp is within the lookback window."""
    ts = _parse_timestamp(ts_str)
    if not ts:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return ts >= cutoff


def _extract_embed(post: dict) -> dict:
    """Extract embed media (images, video thumbnail, link card) from a post."""
    embed = post.get("embed", {})
    embed_type = embed.get("$type", "")

    result = {"embed_type": None, "images": [], "video_thumbnail": None, "external": None}

    if embed_type == "app.bsky.embed.images#view":
        result["embed_type"] = "images"
        for img in embed.get("images", []):
            thumb = img.get("thumb", "")
            alt = img.get("alt", "")
            if thumb:
                result["images"].append({"url": thumb, "alt": alt})

    elif embed_type == "app.bsky.embed.video#view":
        result["embed_type"] = "video"
        result["video_thumbnail"] = embed.get("thumbnail", "")

    elif embed_type == "app.bsky.embed.external#view":
        ext = embed.get("external", {})
        result["embed_type"] = "external"
        result["external"] = {
            "title": ext.get("title", ""),
            "description": ext.get("description", ""),
            "uri": ext.get("uri", ""),
            "thumb": ext.get("thumb", ""),
        }

    # Handle record-with-media (quote post + images/video)
    elif embed_type == "app.bsky.embed.recordWithMedia#view":
        media = embed.get("media", {})
        media_type = media.get("$type", "")
        if media_type == "app.bsky.embed.images#view":
            result["embed_type"] = "images"
            for img in media.get("images", []):
                thumb = img.get("thumb", "")
                alt = img.get("alt", "")
                if thumb:
                    result["images"].append({"url": thumb, "alt": alt})
        elif media_type == "app.bsky.embed.video#view":
            result["embed_type"] = "video"
            result["video_thumbnail"] = media.get("thumbnail", "")

    return result


def _extract_post(post_view: dict, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> Optional[dict]:
    """Extract normalized post data from a Bluesky post view."""
    post = post_view.get("post", post_view)
    record = post.get("record", {})
    author = post.get("author", {})

    created_at = record.get("createdAt", "")
    if not _is_recent(created_at, hours=lookback_hours):
        return None

    handle = author.get("handle", "unknown")
    display_name = author.get("displayName", handle)

    # Extract rkey from the post URI: at://did:plc:xxx/app.bsky.feed.post/rkey
    uri = post.get("uri", "")
    rkey = uri.split("/")[-1] if uri else ""

    # Engagement: likes + reposts + replies
    like_count = post.get("likeCount", 0)
    repost_count = post.get("repostCount", 0)
    reply_count = post.get("replyCount", 0)
    engagement = like_count + repost_count + reply_count

    text = record.get("text", "").strip()
    if not text:
        return None

    # Only include English posts
    langs = record.get("langs", [])
    if langs and "en" not in langs:
        return None

    # Extract embed media
    embed_data = _extract_embed(post)

    return {
        "type": "bluesky",
        "source": "Bluesky",
        "author": handle,
        "display_name": display_name,
        "text": text,
        "url": _post_url(handle, rkey),
        "engagement": engagement,
        "like_count": like_count,
        "repost_count": repost_count,
        "timestamp": created_at,
        "embed_type": embed_data["embed_type"],
        "images": embed_data["images"],
        "video_thumbnail": embed_data["video_thumbnail"],
        "external": embed_data["external"],
    }


def fetch_account_posts(handle: str, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[dict]:
    """Fetch recent posts from a specific Bluesky account."""
    posts = []
    try:
        resp = requests.get(
            f"{BASE_URL}/app.bsky.feed.getAuthorFeed",
            params={"actor": handle, "limit": 30, "filter": "posts_no_replies"},
            timeout=15,
        )
        resp.raise_for_status()
        feed = resp.json().get("feed", [])
        for item in feed:
            post = _extract_post(item, lookback_hours=lookback_hours)
            if post:
                posts.append(post)
    except requests.RequestException as e:
        print(f"  Warning: Failed to fetch Bluesky account @{handle}: {e}")
    return posts


def _create_session() -> Optional[str]:
    """
    Create an authenticated Bluesky session. Returns access token or None.

    Requires BSKY_HANDLE and BSKY_APP_PASSWORD environment variables.
    Get an app password at: https://bsky.app/settings/app-passwords
    """
    handle = os.environ.get("BSKY_HANDLE")
    password = os.environ.get("BSKY_APP_PASSWORD")
    if not handle or not password:
        return None

    try:
        resp = requests.post(
            f"{AUTH_URL}/com.atproto.server.createSession",
            json={"identifier": handle, "password": password},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("accessJwt")
    except requests.RequestException as e:
        print(f"  Warning: Bluesky auth failed: {e}")
        return None


def search_topic_posts(query: str, auth_token: Optional[str] = None, limit: int = 25, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[dict]:
    """Search Bluesky for trending posts on a topic. Requires auth token."""
    if not auth_token:
        return []

    posts = []
    try:
        resp = requests.get(
            f"{AUTH_URL}/app.bsky.feed.searchPosts",
            params={"q": query, "sort": "top", "limit": limit, "lang": "en"},
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("posts", [])
        for item in results:
            post = _extract_post(item, lookback_hours=lookback_hours)
            if post:
                posts.append(post)
    except requests.RequestException as e:
        print(f"  Warning: Failed to search Bluesky for '{query}': {e}")
    return posts


def fetch_bluesky(config: dict, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[dict]:
    """
    Fetch all Bluesky content based on config.

    Returns a list of normalized post dicts, deduplicated by URL.
    Applies noise filtering and engagement thresholds for topic search.
    """
    all_posts = []
    seen_urls = set()

    # Compile skip patterns once
    raw_patterns = config.get("skip_patterns", [])
    skip_patterns = _compile_skip_patterns(raw_patterns) if raw_patterns else []
    min_topic_engagement = config.get("min_topic_engagement", 0)

    skipped_noise = 0

    # Fetch from specific accounts (no auth needed)
    accounts = config.get("accounts", [])
    print(f"Fetching Bluesky posts from {len(accounts)} accounts...")
    for handle in accounts:
        posts = fetch_account_posts(handle, lookback_hours=lookback_hours)
        for post in posts:
            if post["url"] in seen_urls:
                continue
            if skip_patterns and _should_skip(post["text"], skip_patterns):
                skipped_noise += 1
                continue
            seen_urls.add(post["url"])
            all_posts.append(post)

    # Search by topic (requires auth)
    topics = config.get("topics", [])
    if topics:
        auth_token = _create_session()
        if auth_token:
            print(f"Searching Bluesky for {len(topics)} topics (min engagement: {min_topic_engagement})...")
            topic_found = 0
            topic_filtered = 0
            for topic in topics:
                posts = search_topic_posts(topic, auth_token=auth_token, limit=15, lookback_hours=lookback_hours)
                for post in posts:
                    if post["url"] in seen_urls:
                        continue
                    if skip_patterns and _should_skip(post["text"], skip_patterns):
                        skipped_noise += 1
                        continue
                    if post["engagement"] < min_topic_engagement:
                        topic_filtered += 1
                        continue
                    seen_urls.add(post["url"])
                    post["topic"] = topic
                    all_posts.append(post)
                    topic_found += 1
            print(f"  Topic search: {topic_found} quality posts kept, {topic_filtered} below engagement threshold")
        else:
            print("  Skipping topic search (set BSKY_HANDLE and BSKY_APP_PASSWORD to enable)")

    if skipped_noise:
        print(f"  Filtered out {skipped_noise} noise posts (job ads, self-promo, etc.)")

    # Sort by engagement (highest first)
    all_posts.sort(key=lambda p: p["engagement"], reverse=True)

    print(f"Total Bluesky posts (last {lookback_hours}h): {len(all_posts)}")
    return all_posts
