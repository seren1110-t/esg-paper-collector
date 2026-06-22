"""Semantic Scholar collector — ESG papers via public API (no key needed).

Rate limit: 1 req/sec without API key. We space requests with a small delay.
"""

import urllib.request
import urllib.parse
import json
import time
from datetime import datetime, timedelta
from typing import List
from models import Paper


API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,abstract,year,externalIds,publicationDate,openAccessPdf,url"

QUERIES = [
    "ESG climate change corporate sustainability",
    "carbon neutrality net zero emission reduction",
]
_REQUEST_DELAY = 1.5  # seconds between requests


def _search(query: str, limit: int = 20, year: int | None = None) -> List[dict]:
    params: dict = {
        "query": query,
        "limit": limit,
        "fields": FIELDS,
    }
    if year:
        params["year"] = str(year)
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ESG-Collector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("data", [])
    except Exception:
        return []


def collect(days_back: int = 1) -> List[Paper]:
    current_year = datetime.utcnow().year
    seen: set = set()
    papers: List[Paper] = []

    for i, query in enumerate(QUERIES):
        if i > 0:
            time.sleep(_REQUEST_DELAY)
        for item in _search(query, limit=20, year=current_year):
            pid = item.get("paperId", "")
            if pid in seen:
                continue
            seen.add(pid)

            pub_date = item.get("publicationDate") or f"{item.get('year', '')}-01-01"
            try:
                dt = datetime.strptime(pub_date[:10], "%Y-%m-%d").date()
                if dt < (datetime.utcnow() - timedelta(days=days_back)).date():
                    continue
            except ValueError:
                pass

            authors = [a.get("name", "") for a in item.get("authors", [])]
            pdf = (item.get("openAccessPdf") or {}).get("url", "")
            link = pdf or item.get("url") or f"https://www.semanticscholar.org/paper/{pid}"

            papers.append(Paper(
                source="Semantic Scholar",
                title=(item.get("title") or "").strip(),
                authors=authors,
                abstract=(item.get("abstract") or "")[:500],
                url=link,
                published_date=pub_date[:10],
            ))
    return papers
