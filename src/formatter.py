"""Combine, dedupe, and prepare digest data for the email template."""

from datetime import datetime, timezone


def format_digest(
    rss_posts: list[dict],
    config: dict,
) -> dict:
    """
    Prepare the final digest data for the email template.

    Deduplicates by URL, caps items per section, and adds metadata.
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

    # Cap per section
    deduped_rss = deduped_rss[:max_items]

    # Build date string
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A, %B %-d, %Y")

    # Build subject line
    total = len(deduped_rss)
    subject = f"{subject_prefix} — {date_str}"

    return {
        "subject": subject,
        "date": date_str,
        "rss_posts": deduped_rss,
        "total_items": total,
    }
