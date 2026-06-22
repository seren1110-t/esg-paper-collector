"""SSRN collector — ESG/finance/policy working papers via web scraping."""

import urllib.request
import urllib.parse
import re
import json
from datetime import datetime, timedelta
from typing import List
from models import Paper


SEARCH_URL = "https://papers.ssrn.com/sol3/results.cfm"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SEARCH_TERMS = [
    "ESG climate carbon",
    "carbon neutrality sustainability policy",
    "net zero greenhouse gas corporate",
]


def _search(term: str) -> str:
    params = urllib.parse.urlencode({
        "form_name": "journalBrowse",
        "journal_id": "",
        "Network": "no",
        "SortOrder": "SubmissionDate",
        "subjectGroupsSelected": "",
        "txtDate_From": (datetime.utcnow() - timedelta(days=7)).strftime("%m/%d/%Y"),
        "txtDate_To": datetime.utcnow().strftime("%m/%d/%Y"),
        "strSearch": term,
    })
    url = f"{SEARCH_URL}?{params}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _parse(html: str) -> List[dict]:
    results: List[dict] = []
    # Extract paper blocks — SSRN uses consistent class names
    blocks = re.findall(
        r'<div class="title">(.*?)</div>.*?'
        r'href="(https://papers\.ssrn\.com/sol3/papers\.cfm\?[^"]+)".*?'
        r'<div class="authors">(.*?)</div>.*?'
        r'<div class="date">(.*?)</div>',
        html,
        re.DOTALL,
    )
    for title_raw, url, authors_raw, date_raw in blocks:
        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        authors_text = re.sub(r"<[^>]+>", "", authors_raw).strip()
        authors = [a.strip() for a in authors_text.split(",") if a.strip()]
        date_text = re.sub(r"<[^>]+>", "", date_raw).strip()
        results.append({
            "title": title,
            "url": url.strip(),
            "authors": authors,
            "date": date_text,
        })
    return results


def collect(days_back: int = 7) -> List[Paper]:
    """SSRN은 daily보다 weekly 수집이 안정적 — 기본 7일."""
    seen: set = set()
    papers: List[Paper] = []

    for term in SEARCH_TERMS:
        html = _search(term)
        for item in _parse(html):
            url = item["url"]
            if url in seen or not item["title"]:
                continue
            seen.add(url)
            papers.append(Paper(
                source="SSRN",
                title=item["title"],
                authors=item["authors"],
                abstract="",
                url=url,
                published_date=item["date"],
            ))
    return papers
