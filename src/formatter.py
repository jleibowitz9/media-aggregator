"""Combine, dedupe, and prepare digest data for the email template."""

from datetime import datetime, timezone


def format_digest(
    bluesky_posts: list[dict],
    rss_posts: list[dict],
    config: dict,
) -> dict:
    """
    Prepare the final digest data for the email template.

    Deduplicates by URL, caps items per section, and adds metadata.
    """
    max_items = config.get("max_items_per_section", 10)
    subject_prefix = config.get("subject_prefix", "Media Digest")

    # Dedupe across all sources by URL
    seen_urls = set()
    deduped_bluesky = []
    deduped_rss = []

    for post in rss_posts:
        url = post.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped_rss.append(post)

    for post in bluesky_posts:
        url = post.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped_bluesky.append(post)

    # Cap per section
    deduped_rss = deduped_rss[:max_items]
    deduped_bluesky = deduped_bluesky[:max_items]

    # Build date string
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %-d, %Y")

    # Build subject line
    total = len(deduped_rss) + len(deduped_bluesky)
    subject = f"{subject_prefix} — {date_str}"

    return {
        "subject": subject,
        "date": date_str,
        "rss_posts": deduped_rss,
        "bluesky_posts": deduped_bluesky,
        "total_items": total,
    }
