from __future__ import annotations

import asyncio
import html as html_lib
import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailNotConfigured(RuntimeError):
    pass


class EmailSendError(RuntimeError):
    pass


def _format_delta(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}"


def _format_score(value: float | None, label: str) -> str:
    if value is None:
        return label
    return f"{value:.0f}"


def render_digest_email(digest: dict) -> tuple[str, str, str]:
    """Return ``(subject, text, html)`` for a digest payload.

    All external strings (titles, author names, security names) are escaped
    before being interpolated into HTML.
    """
    date = digest.get("date") or ""
    nickname = digest.get("user", {}).get("nickname") or "投资者"
    subject = f"Research Scout 每日简报 · {date}"
    base = settings.frontend_base_url.rstrip("/")
    digest_url = f"{base}/digest?date={date}"

    updates = digest.get("followed_updates") or []
    changes = digest.get("watchlist_changes") or []
    gaps = digest.get("evidence_gaps") or []
    recommended = digest.get("recommended_authors") or []

    text_lines = [f"{nickname}，这是 {date} 的投资研究简报。", ""]

    text_lines.append("一、关注作者更新")
    if updates:
        for item in updates:
            author = (item.get("author") or {}).get("name") or "未知作者"
            text_lines.append(f"- [{author}] {item.get('title') or ''}")
    else:
        text_lines.append("- 今天关注作者没有新内容。")

    text_lines.append("")
    text_lines.append("二、自选股评分变化")
    if changes:
        for item in changes:
            security = item.get("security") or {}
            label = item.get("display_label") or "综合得分"
            delta = _format_delta(item.get("score_delta"))
            score = _format_score(item.get("display_score"), label)
            text_lines.append(
                f"- {security.get('name') or ''}：{score}（{label}），"
                f"较上次 {delta}"
            )
    else:
        text_lines.append("- 暂无自选股。")

    text_lines.append("")
    text_lines.append("三、证据缺口")
    if gaps:
        for item in gaps:
            security = item.get("security") or {}
            text_lines.append(
                f"- {security.get('name') or ''}：{'、'.join(item.get('gaps') or [])}"
            )
    else:
        text_lines.append("- 暂无证据缺口。")

    text_lines.append("")
    text_lines.append("四、推荐作者")
    if recommended:
        for author in recommended:
            text_lines.append(f"- {author.get('canonical_name') or ''}")
    else:
        text_lines.append("- 暂无推荐。")

    text_lines.append("")
    text_lines.append(f"查看完整简报：{digest_url}")
    text_lines.append(f"管理邮件订阅：{base}/settings")
    text = "\n".join(text_lines)

    parts: list[str] = []
    parts.append('<div style="font-family:-apple-system,BlinkMacSystemFont,')
    parts.append("'Segoe UI',sans-serif;max-width:640px;margin:0 auto;color:#1f2937;")
    parts.append('line-height:1.6;padding:16px">')
    parts.append(
        f'<h2 style="margin:0 0 4px">Research Scout 每日简报</h2>'
        f'<p style="color:#6b7280;margin:0 0 20px">{html_lib.escape(date)}</p>'
    )
    parts.append(f"<p>{html_lib.escape(nickname)}，以下是今天的投资研究摘要。</p>")
    parts.append(_email_section_title("一、关注作者更新"))
    if updates:
        parts.append("<ul>")
        for item in updates:
            author = (item.get("author") or {}).get("name") or "未知作者"
            parts.append(
                "<li>"
                f"<strong>{html_lib.escape(author)}</strong>："
                f"{html_lib.escape(str(item.get('title') or ''))}"
                "</li>"
            )
        parts.append("</ul>")
    else:
        parts.append("<p>今天关注作者没有新内容。</p>")

    parts.append(_email_section_title("二、自选股评分变化"))
    if changes:
        parts.append("<ul>")
        for item in changes:
            security = item.get("security") or {}
            label = item.get("display_label") or "综合得分"
            score = _format_score(item.get("display_score"), label)
            delta = _format_delta(item.get("score_delta"))
            parts.append(
                "<li>"
                f"{html_lib.escape(str(security.get('name') or ''))}："
                f"{html_lib.escape(score)}（{html_lib.escape(label)}），"
                f"较上次 {html_lib.escape(delta)}"
                "</li>"
            )
        parts.append("</ul>")
    else:
        parts.append("<p>暂无自选股。</p>")

    parts.append(_email_section_title("三、证据缺口"))
    if gaps:
        parts.append("<ul>")
        for item in gaps:
            security = item.get("security") or {}
            parts.append(
                "<li>"
                f"{html_lib.escape(str(security.get('name') or ''))}："
                f"{html_lib.escape('、'.join(item.get('gaps') or []))}"
                "</li>"
            )
        parts.append("</ul>")
    else:
        parts.append("<p>暂无证据缺口。</p>")

    parts.append(_email_section_title("四、推荐作者"))
    if recommended:
        parts.append("<ul>")
        for author in recommended:
            parts.append(
                f"<li>{html_lib.escape(str(author.get('canonical_name') or ''))}</li>"
            )
        parts.append("</ul>")
    else:
        parts.append("<p>暂无推荐。</p>")

    parts.append(
        f'<p style="margin-top:24px"><a href="{html_lib.escape(digest_url)}" '
        'style="background:#2563eb;color:#fff;padding:10px 16px;border-radius:6px;'
        'text-decoration:none">查看完整简报</a></p>'
    )
    parts.append(
        f'<p style="color:#9ca3af;font-size:12px;margin-top:24px">'
        f'不想收到邮件？<a href="{html_lib.escape(base)}/settings">前往设置关闭</a>'
        "</p>"
    )
    parts.append("</div>")
    html = "".join(parts)
    return subject, text, html


def _email_section_title(title: str) -> str:
    return f'<h3 style="margin:20px 0 8px">{html_lib.escape(title)}</h3>'


def _send_sync(message: EmailMessage) -> None:
    if settings.smtp_ssl:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=20
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
    try:
        client.ehlo()
        if settings.smtp_starttls and not settings.smtp_ssl:
            client.starttls()
            client.ehlo()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001 - best-effort close
            client.close()


async def send_email(
    to_email: str,
    subject: str,
    text: str,
    html: str,
) -> None:
    if not settings.smtp_host:
        raise EmailNotConfigured("SMTP_HOST is not configured")

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message["Subject"] = subject
    base = settings.frontend_base_url.rstrip("/")
    message["List-Unsubscribe"] = f"<{base}/settings>"
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        await asyncio.to_thread(_send_sync, message)
    except Exception as exc:  # noqa: BLE001 - SMTP failures are recorded by the caller
        raise EmailSendError(str(exc)[:500]) from exc


__all__ = [
    "EmailNotConfigured",
    "EmailSendError",
    "render_digest_email",
    "send_email",
]
