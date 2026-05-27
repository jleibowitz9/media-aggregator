"""Fetch recent posts from RSS feeds using feedparser."""

import html
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser

DEFAULT_LOOKBACK_HOURS = 24


def _parse_pub_date(entry: dict) -> Optional[datetime]:
    """Parse the publication date from an RSS entry."""
    # feedparser normalizes dates into 'published_parsed' or 'updated_parsed'
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                # struct_time → datetime (feedparser gives UTC)
                from time import mktime
                from calendar import timegm
                dt = datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)
                return dt
            except (ValueError, OverflowError, OSError):
                continue

    # Fallback: try raw string parsing
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw)
            except (ValueError, TypeError):
                continue

    return None


def _is_recent(entry: dict, hours: int = DEFAULT_LOOKBACK_HOURS) -> bool:
    """Check if an RSS entry is within the lookback window."""
    pub_date = _parse_pub_date(entry)
    if not pub_date:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return pub_date >= cutoff


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_entry(entry: dict, feed_name: str, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> Optional[dict]:
    """Extract normalized post data from an RSS feed entry."""
    if not _is_recent(entry, hours=lookback_hours):
        return None

    title = entry.get("title", "").strip()
    link = entry.get("link", "").strip()
    if not title or not link:
        return None

    # Get description — try summary first, then content
    description = ""
    if entry.get("summary"):
        description = _strip_html(entry["summary"])
    elif entry.get("content"):
        for content_item in entry["content"]:
            if content_item.get("value"):
                description = _strip_html(content_item["value"])
                break

    # Truncate description to a reasonable length
    if len(description) > 200:
        description = description[:197] + "..."

    pub_date = _parse_pub_date(entry)
    timestamp = pub_date.isoformat() if pub_date else ""

    return {
        "type": "rss",
        "source": feed_name,
        "title": title,
        "description": description,
        "url": link,
        "timestamp": timestamp,
        "author": entry.get("author", ""),
    }


def fetch_feed(feed_url: str, feed_name: str, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[dict]:
    """Fetch and parse a single RSS feed, returning recent entries."""
    posts = []
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            print(f"  Warning: Failed to parse feed '{feed_name}': {feed.bozo_exception}")
            return posts

        for entry in feed.entries:
            post = _extract_entry(entry, feed_name, lookback_hours=lookback_hours)
            if post:
                posts.append(post)

    except Exception as e:
        print(f"  Warning: Error fetching feed '{feed_name}': {e}")

    return posts


def fetch_rss(config: dict, lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[dict]:
    """
    Fetch all RSS content based on config.

    Returns a list of normalized post dicts sorted by timestamp (newest first).
    """
    all_posts = []
    feeds = config.get("feeds", [])

    print(f"Fetching RSS posts from {len(feeds)} feeds...")
    for feed_config in feeds:
        url = feed_config.get("url", "")
        name = feed_config.get("name", url)
        posts = fetch_feed(url, name, lookback_hours=lookback_hours)
        all_posts.extend(posts)
        if posts:
            print(f"  {name}: {len(posts)} new posts")
        else:
            print(f"  {name}: no new posts in last {lookback_hours}h")

    # Sort by timestamp (newest first)
    all_posts.sort(key=lambda p: p.get("timestamp", ""), reverse=True)

    print(f"Total RSS posts (last {lookback_hours}h): {len(all_posts)}")
    return all_posts
