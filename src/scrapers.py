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
        if not pub_date or pub_date < cutoff:
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
