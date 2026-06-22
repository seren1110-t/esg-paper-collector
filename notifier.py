"""알림 발송 — Gmail SMTP 이메일 + Slack Webhook."""

import os
import smtplib
import urllib.request
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import List


# ── 환경 변수 ──────────────────────────────────────────────────
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = os.getenv("SMTP_USER", "")          # Gmail 주소
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")      # Gmail 앱 비밀번호
NOTIFY_EMAIL  = os.getenv("NOTIFY_EMAIL", "")       # 수신 이메일
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK", "")      # Slack Incoming Webhook URL


# ── 이메일 ──────────────────────────────────────────────────────

def _build_html(results: List[dict], date_str: str, stats: dict) -> str:
    """요약 결과 → HTML 이메일 본문."""
    rows = ""
    for i, item in enumerate(results[:50], 1):
        s = item.get("summary") or {}
        one_liner = s.get("one_liner", "-")
        implications = s.get("esg_implications") or []
        impl_html = "".join(f"<li>{x}</li>" for x in implications[:3])
        rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:12px 8px;color:#888;font-size:12px;vertical-align:top">{i}</td>
          <td style="padding:12px 8px;vertical-align:top">
            <div style="font-weight:700;font-size:13px;margin-bottom:4px">
              <a href="{item['url']}" style="color:#1a56db;text-decoration:none">{item['title'][:100]}</a>
            </div>
            <div style="font-size:11px;color:#666;margin-bottom:6px">
              {item['source']} · {item.get('published_date','')}
            </div>
            <div style="background:#f0f7ff;border-left:3px solid #1a56db;padding:6px 10px;
                        font-size:12px;color:#1e3a5f;margin-bottom:6px;border-radius:0 4px 4px 0">
              📌 {one_liner}
            </div>
            <ul style="margin:0;padding-left:18px;font-size:12px;color:#444;line-height:1.7">
              {impl_html}
            </ul>
          </td>
        </tr>"""

    return f"""
    <html><body style="font-family:-apple-system,sans-serif;background:#f8f9fa;margin:0;padding:20px">
    <div style="max-width:700px;margin:0 auto;background:#fff;border-radius:12px;
                box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden">
      <div style="background:#1a56db;padding:24px 28px">
        <h1 style="color:#fff;margin:0;font-size:20px">🌿 ESG 논문 브리핑</h1>
        <div style="color:#93c5fd;font-size:13px;margin-top:6px">{date_str} · Gemini 3 Flash 한국어 요약</div>
      </div>
      <div style="padding:16px 28px;background:#f0f7ff;border-bottom:1px solid #dbeafe">
        <span style="font-size:13px;color:#1e3a5f">
          📊 수집 <b>{stats.get('collected',0)}건</b> →
          필터링 <b>{stats.get('filtered',0)}건</b> →
          요약 <b>{stats.get('summarized',0)}건</b>
        </span>
      </div>
      <table style="width:100%;border-collapse:collapse;padding:0 28px">
        {rows}
      </table>
      <div style="padding:16px 28px;background:#f8f9fa;font-size:11px;color:#999;text-align:center">
        ESG Paper Collector · GitHub Actions 자동화
      </div>
    </div>
    </body></html>"""


def send_email(results: List[dict], date_str: str, stats: dict) -> bool:
    """HTML 이메일 발송. 성공 시 True."""
    if not all([SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL]):
        print("  [SKIP] 이메일 환경변수 미설정 (SMTP_USER / SMTP_PASSWORD / NOTIFY_EMAIL)")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[ESG 브리핑] {date_str} · {stats.get('summarized', 0)}건 요약"
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(_build_html(results, date_str, stats), "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())
        print(f"  [OK] 이메일 발송 → {NOTIFY_EMAIL}")
        return True
    except Exception as e:
        print(f"  [ERROR] 이메일 발송 실패: {e}")
        return False


# ── Slack ───────────────────────────────────────────────────────

def _build_slack_payload(results: List[dict], date_str: str, stats: dict) -> dict:
    top5 = results[:5]
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🌿 ESG 논문 브리핑 — {date_str}"}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn",
                "text": f"수집 *{stats.get('collected',0)}건* → 필터 *{stats.get('filtered',0)}건* → 요약 *{stats.get('summarized',0)}건*"}]
        },
        {"type": "divider"},
    ]

    for i, item in enumerate(top5, 1):
        s = item.get("summary") or {}
        one_liner = s.get("one_liner", "-")
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{i}. <{item['url']}|{item['title'][:80]}>*\n"
                    f"_{item['source']} · {item.get('published_date','')}_\n"
                    f"📌 {one_liner}"
                )
            }
        })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "ESG Paper Collector · GitHub Actions"}]
    })
    return {"blocks": blocks}


def send_slack(results: List[dict], date_str: str, stats: dict) -> bool:
    """Slack Webhook 발송. 성공 시 True."""
    if not SLACK_WEBHOOK:
        print("  [SKIP] SLACK_WEBHOOK 미설정")
        return False

    payload = json.dumps(_build_slack_payload(results, date_str, stats)).encode()
    req = urllib.request.Request(
        SLACK_WEBHOOK,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 200:
                print("  [OK] Slack 발송 완료")
                return True
    except Exception as e:
        print(f"  [ERROR] Slack 발송 실패: {e}")
    return False


def send_error_alert(error_msg: str) -> None:
    """파이프라인 실패 시 Slack 에러 알림."""
    if not SLACK_WEBHOOK:
        return
    payload = json.dumps({
        "text": f"🚨 *ESG Collector 실패*\n```{error_msg[:500]}```"
    }).encode()
    req = urllib.request.Request(
        SLACK_WEBHOOK,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def notify_all(results: List[dict], date_str: str, stats: dict) -> None:
    """이메일 + Slack 동시 발송."""
    send_email(results, date_str, stats)
    send_slack(results, date_str, stats)
