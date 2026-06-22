"""OpenAlex collector — keyword 검색 기반 ESG 논문 수집."""

import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta
from typing import List
from models import Paper


API_BASE = "https://api.openalex.org/works"

KEYWORDS = [
    "climate change",
    "carbon neutrality",
    "ESG sustainability",
    "greenhouse gas emission",
    "net zero renewable energy",
]


def _fetch(keyword: str, from_date: str, per_page: int = 20) -> List[dict]:
    params = {
        "search": keyword,
        "filter": f"from_publication_date:{from_date}",
        "sort": "publication_date:desc",
        "per-page": per_page,
        "select": "id,title,authorships,abstract_inverted_index,publication_date,doi,open_access,primary_location",
        "mailto": "esg-collector@example.com",
    }
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ESG-Collector/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()).get("results", [])
    except Exception:
        return []


def _reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    try:
        max_pos = max(max(v) for v in inverted.values())
        words: list = [""] * (max_pos + 1)
        for word, positions in inverted.items():
            for pos in positions:
                words[pos] = word
        return " ".join(words)[:500]
    except Exception:
        return ""


def collect(days_back: int = 1) -> List[Paper]:
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    seen: set = set()
    papers: List[Paper] = []

    for keyword in KEYWORDS:
        for item in _fetch(keyword, from_date, per_page=20):
            oa_id = item.get("id", "")
            if oa_id in seen:
                continue
            seen.add(oa_id)

            title = (item.get("title") or "").strip()
            if not title:
                continue

            authors = [
                a.get("author", {}).get("display_name", "")
                for a in item.get("authorships", [])[:5]
            ]
            doi = item.get("doi") or ""
            # OA PDF URL: open_access.oa_url 우선, 없으면 DOI
            oa_info = item.get("open_access") or {}
            oa_url = oa_info.get("oa_url") or ""
            url = oa_url if oa_url else (doi if doi else oa_id)
            abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
            pub_date = (item.get("publication_date") or "")[:10]

            # 6개월 초과 미래 날짜 제외 (저널 in-press 허용)
            try:
                if pub_date and datetime.strptime(pub_date, "%Y-%m-%d") > datetime.utcnow() + timedelta(days=180):
                    continue
            except ValueError:
                pass

            papers.append(Paper(
                source="OpenAlex",
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                published_date=pub_date,
            ))
    return papers
