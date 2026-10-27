"""Scrape update pages that don't offer RSS feeds."""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

DEFAULT_LOOKBACK_HOURS = 24
FRAMER_UPDATES_URL = "https://www.framer.com/updates"


def fetch_framer_updates(lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[dict]:
    """Scrape recent entries from Framer's /updates page."""
    posts = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        resp = requests.get(FRAMER_UPDATES_URL, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"  # avoid mojibake in apostrophes/quotes
    except requests.RequestException as e:
        print(f"  Warning: Failed to fetch Framer updates: {e}")
        return posts

    soup = BeautifulSoup(resp.text, "html.parser")
    sections = soup.select('section[data-framer-name="Post"]')

    for section in sections:
        title_link = section.select_one('a[data-styles-preset="uexyNUZEC"]')
        time_tag = section.select_one("time[datetime]")
        desc_div = section.select_one('div[data-framer-name="Content"]')

        if not title_link or not time_tag:
            continue

        title = title_link.get_text(strip=True)
        href = title_link.get("href", "")
        if href.startswith("./"):
            href = FRAMER_UPDATES_URL.rstrip("/") + href[1:]
        elif href.startswith("/"):
            href = "https://www.framer.com" + href

        dt_str = time_tag.get("datetime", "")
        pub_date = _parse_iso(dt_str)
        if not pub_date:
            continue
        # Framer stamps each update with a date only (midnight UTC) but publishes
        # them throughout the day. Comparing that midnight timestamp against a
        # rolling lookback means an update posted after the daily run time looks
        # >24h old on the next run and gets skipped forever. Treat the timestamp
        # as end-of-day so an update is reliably caught by the following run.
        effective_date = pub_date.replace(hour=23, minute=59, second=59)
        if effective_date < cutoff:
            continue

        description = ""
        if desc_div:
            paragraphs = desc_div.find_all("p", class_="framer-text")
            texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            description = " ".join(texts)
            if len(description) > 200:
                description = description[:197] + "..."

        posts.append({
            "type": "rss",
            "source": "Framer Updates",
            "title": title,
            "description": description,
            "url": href,
            "timestamp": pub_date.isoformat(),
            "author": "",
        })

    if posts:
        print(f"  Framer Updates: {len(posts)} new updates")
    else:
        print(f"  Framer Updates: no new updates in last {lookback_hours}h")

    return posts


def _parse_iso(dt_str: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp to UTC datetime."""
    try:
        dt_str = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return None


AIRBNB_NEWSROOM_URL = "https://news.airbnb.com"
AIRBNB_PRODUCT_URL = f"{AIRBNB_NEWSROOM_URL}/category/product/"


def fetch_airbnb_product(lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[dict]:
    """
    Scrape recent posts from Airbnb's newsroom Product category.

    Airbnb retired its WordPress RSS feed when the newsroom moved to Next.js —
    https://news.airbnb.com/feed now hard-404s — so this reads the category
    listing directly. Product news ships infrequently (often weeks apart), so
    an empty result is the normal case, not a failure.
    """
    posts = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        resp = requests.get(AIRBNB_PRODUCT_URL, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"  # avoid mojibake in apostrophes/quotes
    except requests.RequestException as e:
        print(f"  Warning: Failed to fetch Airbnb Product news: {e}")
        return posts

    soup = BeautifulSoup(resp.text, "html.parser")

    for time_tag in soup.find_all("time"):
        # html.parser lowercases attributes, so dateTime -> datetime
        dt_str = (time_tag.get("datetime") or "").strip()
        if not dt_str:
            continue
        try:
            pub_date = datetime.fromisoformat(dt_str)
        except ValueError:
            continue
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)
        if pub_date < cutoff:
            continue

        # Walk up from the <time> to the card wrapper holding the headline link
        link, node = None, time_tag
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            link = node.find("a", href=True)
            if link:
                break
        if not link:
            continue

        title = link.get_text(strip=True)
        href = link["href"]
        if href.startswith("/"):
            href = AIRBNB_NEWSROOM_URL + href
        if not title or not href.startswith("http"):
            continue

        posts.append({
            "type": "rss",
            "source": "Airbnb Product",
            "title": title,
            "description": "",
            "url": href,
            "timestamp": pub_date.isoformat(),
            "author": "",
        })

    if posts:
        print(f"  Airbnb Product: {len(posts)} new posts")
    else:
        print(f"  Airbnb Product: no new posts in last {lookback_hours}h")

    return posts
