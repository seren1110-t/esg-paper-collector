"""CrossRef collector — ESG/climate 저널 논문 (Wiley, Elsevier 등 포함)."""

import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta
from typing import List
from models import Paper


API_BASE = "https://api.crossref.org/works"

QUERIES = [
    "ESG corporate sustainability climate",
    "carbon neutrality net zero policy",
    "greenhouse gas emission renewable energy",
]

ESG_JOURNALS = [
    "10.1002/(ISSN)1099-0836",   # Business Strategy and the Environment
    "10.1016/j.jclepro",          # Journal of Cleaner Production
    "10.1016/j.envsci",           # Environmental Science & Policy
]


def _search(query: str, from_date: str, rows: int = 20) -> List[dict]:
    params = {
        "query": query,
        "filter": f"from-pub-date:{from_date},type:journal-article",
        "rows": rows,
        "sort": "published",
        "order": "desc",
        "select": "DOI,title,author,abstract,published,container-title",
        "mailto": "esg-collector@example.com",
    }
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ESG-Collector/1.0 (mailto:esg@example.com)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("message", {}).get("items", [])
    except Exception:
        return []


def _parse_date(item: dict) -> str:
    pub = item.get("published", {})
    parts = pub.get("date-parts", [[]])[0]
    if not parts:
        return ""
    year = parts[0] if len(parts) > 0 else ""
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    return f"{year}-{int(month):02d}-{int(day):02d}"


def collect(days_back: int = 1) -> List[Paper]:
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    seen: set = set()
    papers: List[Paper] = []

    for query in QUERIES:
        for item in _search(query, from_date, rows=20):
            doi = item.get("DOI", "")
            if doi in seen:
                continue
            seen.add(doi)

            titles = item.get("title", [])
            title = titles[0].strip() if titles else ""
            if not title:
                continue

            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in item.get("author", [])[:5]
            ]
            abstract = (item.get("abstract") or "").replace("<jats:p>", "").replace("</jats:p>", "")[:500]
            pub_date = _parse_date(item)
            url = f"https://doi.org/{doi}" if doi else ""

            # 6개월 초과 미래 날짜 제외 (저널 in-press 허용)
            try:
                if pub_date and datetime.strptime(pub_date, "%Y-%m-%d") > datetime.utcnow() + timedelta(days=180):
                    continue
            except ValueError:
                pass

            papers.append(Paper(
                source="CrossRef",
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                published_date=pub_date,
            ))
    return papers
