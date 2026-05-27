"""Send or preview the digest email."""

import os
import subprocess
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT_DIR / "templates"
PREVIEW_PATH = ROOT_DIR / "preview.html"


def _render_html(digest_data: dict) -> str:
    """Render the email template with digest data."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("email.html")
    return template.render(**digest_data)


def preview_digest(digest_data: dict) -> None:
    """Write the rendered email to preview.html and open in browser."""
    html = _render_html(digest_data)
    PREVIEW_PATH.write_text(html, encoding="utf-8")
    print(f"\nPreview written to {PREVIEW_PATH}")

    # Try to open in default browser
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(PREVIEW_PATH)], check=True)
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", str(PREVIEW_PATH)], check=True)
        elif sys.platform == "win32":
            os.startfile(str(PREVIEW_PATH))
        print("Opened in browser.")
    except (subprocess.CalledProcessError, OSError, AttributeError):
        print("Could not open browser automatically. Open the file manually.")


def send_digest(digest_data: dict, to_email: str) -> None:
    """Send the digest email via Resend."""
    import resend

    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("Error: RESEND_API_KEY environment variable required")
        sys.exit(1)

    resend.api_key = api_key
    html = _render_html(digest_data)

    try:
        result = resend.Emails.send({
            "from": os.environ.get("FROM_EMAIL", "Media Digest <onboarding@resend.dev>"),
            "to": [to_email],
            "subject": digest_data["subject"],
            "html": html,
        })
        print(f"\nEmail sent successfully! ID: {result.get('id', 'unknown')}")
    except Exception as e:
        print(f"\nError sending email: {e}")
        sys.exit(1)
