"""PubMed collector — environmental health & climate papers via E-utilities."""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List
from models import Paper


ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

QUERY = (
    "(climate change[MeSH] OR carbon emission[tiab] OR ESG[tiab] OR "
    "sustainability[MeSH] OR greenhouse gas[tiab] OR net zero[tiab] OR "
    "renewable energy[MeSH]) AND (\"last 1 days\"[PDat])"
)


def _esearch(days_back: int, retmax: int = 50) -> List[str]:
    mindate = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": QUERY,
        "retmax": retmax,
        "retmode": "json",
        "mindate": mindate,
        "datetype": "pdat",
        "tool": "esg-collector",
        "email": "esg-collector@example.com",
    })
    url = f"{ESEARCH}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            import json
            data = json.loads(resp.read())
            return data.get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []


def _efetch(pmids: List[str]) -> List[Paper]:
    if not pmids:
        return []
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": "esg-collector",
        "email": "esg-collector@example.com",
    })
    url = f"{EFETCH}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return []

    papers: List[Paper] = []
    for article in root.findall(".//PubmedArticle"):
        medline = article.find("MedlineCitation")
        if medline is None:
            continue
        art = medline.find("Article")
        if art is None:
            continue

        title = (art.findtext("ArticleTitle") or "").strip()
        abstract_el = art.find("Abstract/AbstractText")
        abstract = (abstract_el.text or "") if abstract_el is not None else ""

        authors: List[str] = []
        for au in art.findall("AuthorList/Author"):
            last = au.findtext("LastName") or ""
            fore = au.findtext("ForeName") or ""
            if last:
                authors.append(f"{fore} {last}".strip())

        pmid = medline.findtext("PMID") or ""
        pub_date_el = article.find(".//PubMedPubDate[@PubStatus='pubmed']")
        if pub_date_el is not None:
            y = pub_date_el.findtext("Year") or ""
            m = pub_date_el.findtext("Month") or "01"
            d = pub_date_el.findtext("Day") or "01"
            pub_date = f"{y}-{int(m):02d}-{int(d):02d}"
        else:
            pub_date = ""

        papers.append(Paper(
            source="PubMed",
            title=title,
            authors=authors,
            abstract=abstract[:500],
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            published_date=pub_date,
        ))
    return papers


def collect(days_back: int = 1) -> List[Paper]:
    pmids = _esearch(days_back, retmax=50)
    return _efetch(pmids)
