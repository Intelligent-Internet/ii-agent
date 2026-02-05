from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import argparse
import smtplib
import sys
from email.mime.text import MIMEText

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from ii_skills.wealth_macro_newsletter.settings import WealthMacroSettings
from ii_skills.shared import get_skill_config


@dataclass
class Section:
    title: str
    body: str


TEMPLATE_PATH = Path(__file__).parent / "templates" / "newsletter-template.md"


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_sections() -> list[Section]:
    """Return placeholder sections for the initial scaffold."""

    return [
        Section(
            title="Liquidity Regime",
            body="TODO: Compute global liquidity score and recent drivers.",
        ),
        Section(
            title="Changing World Order Lens",
            body="TODO: Summarize cycle indicators, conflict signals, and policy shifts.",
        ),
        Section(
            title="Macro Indicators",
            body="TODO: Highlight growth, inflation, labor, and credit changes.",
        ),
        Section(
            title="Asset Class & Sector Playbook",
            body="TODO: Map regime to asset/sector tilts with rationale.",
        ),
        Section(
            title="Media Watch (Howell, Dalio, etc.)",
            body="TODO: Add new interview/podcast summaries with citations.",
        ),
        Section(
            title="Social Pulse",
            body="TODO: Add daily screenshots from tracked social accounts.",
        ),
    ]


def render_newsletter(sections: list[Section]) -> str:
    template = load_template()
    rendered_sections = "\n\n".join(
        f"## {section.title}\n{section.body}" for section in sections
    )
    return template.replace("{{DATE}}", date.today().isoformat()).replace(
        "{{SECTIONS}}", rendered_sections
    )


def save_newsletter(config: WealthMacroSettings, content: str) -> Path:
    config.ensure_dirs()
    filename = f"{date.today().isoformat()}-wealth-macro-newsletter.md"
    output_path = config.base_dir / "newsletters" / filename
    output_path.write_text(content, encoding="utf-8")
    return output_path


def generate() -> Path:
    """Generate the daily wealth macro newsletter scaffold."""

    config = WealthMacroSettings()
    sections = build_sections()
    content = render_newsletter(sections)
    return save_newsletter(config, content)


def send_email(content: str, subject: str, recipient: str | None = None) -> bool:
    """Send the newsletter via Gmail SMTP using shared skill config."""
    config = get_skill_config()
    email_settings = config.email
    target_recipient = recipient or email_settings.recipient_email

    if not email_settings.sender_email or not email_settings.sender_password:
        print("Missing email credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD.")
        return False

    if not target_recipient:
        print("Missing recipient email. Provide --to or set RECIPIENT_EMAIL.")
        return False

    msg = MIMEText(content, "plain")
    msg["Subject"] = subject
    msg["From"] = email_settings.sender_email
    msg["To"] = target_recipient

    try:
        with smtplib.SMTP(email_settings.smtp_server, email_settings.smtp_port) as server:
            server.starttls()
            server.login(email_settings.sender_email, email_settings.sender_password)
            server.send_message(msg)
        print(f"Newsletter sent to {target_recipient}.")
        return True
    except smtplib.SMTPException as exc:
        print(f"Failed to send email: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Wealth Macro Newsletter")
    parser.add_argument("--send", action="store_true", help="Send the newsletter via email")
    parser.add_argument("--to", help="Override recipient email address")
    parser.add_argument(
        "--subject",
        default=f"Wealth Macro Daily Newsletter - {date.today().isoformat()}",
        help="Email subject line",
    )
    args = parser.parse_args()

    output_path = generate()
    content = output_path.read_text(encoding="utf-8")
    print(f"Newsletter saved to {output_path}")

    if args.send:
        success = send_email(content, args.subject, args.to)
        return 0 if success else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
