"""arXiv collector — ESG/climate/carbon papers via arXiv API."""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List
from models import Paper


ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}

# 제목에서 ESG 핵심어가 포함된 논문만 수집 (관련성 높임)
ESG_QUERY = (
    "ti:climate OR ti:carbon OR ti:ESG OR ti:sustainability OR "
    "ti:greenhouse OR ti:biodiversity"
)


def fetch(query: str, max_results: int = 50, days_back: int = 1) -> List[Paper]:
    since = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y%m%d")
    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"{ARXIV_API}?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    papers: List[Paper] = []
    for entry in root.findall("atom:entry", NS):
        published_raw = (entry.findtext("atom:published", "", NS) or "")[:10]
        try:
            pub_date = datetime.strptime(published_raw, "%Y-%m-%d").date()
        except ValueError:
            continue
        if pub_date < (datetime.utcnow() - timedelta(days=days_back)).date():
            continue

        arxiv_id = (entry.findtext("atom:id", "", NS) or "").strip()
        title = (entry.findtext("atom:title", "", NS) or "").strip().replace("\n", " ")
        summary = (entry.findtext("atom:summary", "", NS) or "").strip().replace("\n", " ")
        authors = [
            a.findtext("atom:name", "", NS) or ""
            for a in entry.findall("atom:author", NS)
        ]
        papers.append(Paper(
            source="arXiv",
            title=title,
            authors=authors,
            abstract=summary[:500],
            url=arxiv_id,
            published_date=published_raw,
        ))
    return papers


def collect(days_back: int = 1) -> List[Paper]:
    return fetch(ESG_QUERY, max_results=50, days_back=days_back)
