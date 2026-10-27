"""Combine, dedupe, and prepare digest data for the email template."""

from datetime import datetime, timezone
from typing import Optional


def format_digest(
    rss_posts: list[dict],
    config: dict,
    source_order: Optional[list[str]] = None,
) -> dict:
    """
    Prepare the final digest data for the email template.

    Deduplicates by URL, caps items per feed and overall, then groups the
    surviving posts into one section per source. Sections follow the order the
    sources are declared in config.yaml; anything unrecognized is appended
    alphabetically so a new source can never silently vanish.
    """
    max_items = config.get("max_items_per_section", 10)
    subject_prefix = config.get("subject_prefix", "Media Digest")

    max_per_feed = config.get("max_items_per_feed", 3)
    per_feed_overrides = config.get("max_items_per_feed_overrides", {})

    # Dedupe across all sources by URL, cap per feed source
    seen_urls = set()
    source_counts: dict[str, int] = {}
    deduped_rss = []

    for post in rss_posts:
        url = post.get("url", "")
        source = post.get("source", "")
        source_limit = per_feed_overrides.get(source, max_per_feed)
        if url and url not in seen_urls:
            if source_counts.get(source, 0) >= source_limit:
                continue
            seen_urls.add(url)
            source_counts[source] = source_counts.get(source, 0) + 1
            deduped_rss.append(post)

    # Cap total items across the digest
    deduped_rss = deduped_rss[:max_items]

    # Group into one section per source, preserving config order
    grouped: dict[str, list[dict]] = {}
    for post in deduped_rss:
        grouped.setdefault(post.get("source", "Other"), []).append(post)

    order = source_order or []
    ordered_names = [n for n in order if n in grouped]
    ordered_names += sorted(n for n in grouped if n not in order)

    sections = [{"source": name, "posts": grouped[name]} for name in ordered_names]

    # Build date string
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %-d, %Y")

    # Build subject line
    total = len(deduped_rss)
    subject = f"{subject_prefix} — {date_str}"

    return {
        "subject": subject,
        "date": date_str,
        "sections": sections,
        "rss_posts": deduped_rss,
        "total_items": total,
    }
