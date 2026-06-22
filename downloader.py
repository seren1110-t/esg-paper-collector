"""PDF downloader for collected ESG papers.

각 소스별 오픈액세스 PDF URL을 찾아 다운로드한다.
- arXiv: abs URL → pdf URL로 변환
- PubMed: PMC OA API로 PDF URL 조회
- OpenAlex: open_access.oa_url 필드 (수집 시 추가)
- 기타: DOI → Unpaywall API로 OA PDF URL 조회
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import os
import re
import time
from typing import Optional
from models import Paper


UNPAYWALL_EMAIL = "esg-collector@example.com"  # Unpaywall API 필수
PMC_OA_API = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}
DOWNLOAD_DELAY = 1.5  # 서버 부하 방지


# ── URL 추출 ──────────────────────────────────────────────────

def _arxiv_pdf_url(paper: Paper) -> Optional[str]:
    """arXiv abs URL → PDF URL 변환."""
    url = paper.url
    # http://arxiv.org/abs/2406.12345v1 → https://arxiv.org/pdf/2406.12345v1
    match = re.search(r"arxiv\.org/abs/([^\s]+)", url)
    if match:
        return f"https://arxiv.org/pdf/{match.group(1)}"
    return None


def _pmc_pdf_url(paper: Paper) -> Optional[str]:
    """PubMed URL에서 PMID 추출 → PMC OA API로 PDF URL 조회."""
    match = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", paper.url)
    if not match:
        return None
    pmid = match.group(1)

    # PMID → PMCID 변환
    conv_url = (
        f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        f"?ids={pmid}&format=json&tool=esg-collector&email={UNPAYWALL_EMAIL}"
    )
    try:
        with urllib.request.urlopen(conv_url, timeout=10) as r:
            data = json.loads(r.read())
        records = data.get("records", [])
        pmcid = records[0].get("pmcid", "") if records else ""
    except Exception:
        return None

    if not pmcid:
        return None

    # PMCID → OA PDF URL
    oa_url = f"{PMC_OA_API}?id={pmcid}&format=pdf"
    try:
        with urllib.request.urlopen(oa_url, timeout=10) as r:
            xml = r.read().decode()
        match = re.search(r'href="([^"]+\.pdf)"', xml)
        if match:
            href = match.group(1)
            # FTP → HTTPS 변환
            href = href.replace("ftp://ftp.ncbi.nlm.nih.gov", "https://ftp.ncbi.nlm.nih.gov")
            return href
    except Exception:
        pass
    return None


def _unpaywall_pdf_url(paper: Paper) -> Optional[str]:
    """DOI → Unpaywall API로 오픈액세스 PDF URL 조회."""
    doi = ""
    if paper.url.startswith("https://doi.org/"):
        doi = paper.url.replace("https://doi.org/", "")
    elif paper.url.startswith("http://doi.org/"):
        doi = paper.url.replace("http://doi.org/", "")
    if not doi:
        return None

    api_url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='')}?email={UNPAYWALL_EMAIL}"
    try:
        req = urllib.request.Request(api_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        best = data.get("best_oa_location") or {}
        return best.get("url_for_pdf") or best.get("url")
    except Exception:
        return None


def _openalex_pdf_url(paper: Paper) -> Optional[str]:
    """OpenAlex: oa_url이 paper.url에 저장되어 있으면 그대로 사용,
    DOI면 Unpaywall 조회."""
    url = paper.url
    if url.endswith(".pdf") or "pdf" in url.lower():
        return url
    if url.startswith("https://doi.org/"):
        return _unpaywall_pdf_url(paper)
    # openalex.org ID → Unpaywall 불가, 스킵
    return None


def get_pdf_url(paper: Paper) -> Optional[str]:
    """소스별 PDF URL 탐색 우선순위."""
    if paper.source == "arXiv":
        return _arxiv_pdf_url(paper)
    elif paper.source == "PubMed":
        return _pmc_pdf_url(paper)
    elif paper.source in ("OpenAlex", "CrossRef"):
        return _openalex_pdf_url(paper)
    elif paper.source == "Semantic Scholar":
        # openAccessPdf URL이 paper.url에 저장된 경우
        if paper.url.endswith(".pdf"):
            return paper.url
        return _unpaywall_pdf_url(paper)
    return None


# ── 다운로드 ──────────────────────────────────────────────────

def _safe_filename(title: str, max_len: int = 80) -> str:
    """제목 → 파일명 변환 (특수문자 제거)."""
    name = re.sub(r'[\\/:*?"<>|]', "", title)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:max_len]


def download_pdf(pdf_url: str, dest_path: str) -> bool:
    """PDF를 dest_path에 저장. 성공 시 True."""
    try:
        req = urllib.request.Request(pdf_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()

        # PDF 시그니처 확인
        if not data.startswith(b"%PDF"):
            return False

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return False


def download_papers(
    papers: list[Paper],
    base_dir: str = "output/pdfs",
    max_papers: int = 50,
    delay: float = DOWNLOAD_DELAY,
) -> dict:
    """
    논문 목록에서 PDF를 찾아 다운로드한다.

    Returns:
        {"downloaded": [...], "no_pdf": [...], "failed": [...]}
    """
    results = {"downloaded": [], "no_pdf": [], "failed": []}
    attempted = 0

    for paper in papers:
        if attempted >= max_papers:
            break

        pdf_url = get_pdf_url(paper)
        if not pdf_url:
            results["no_pdf"].append(paper.title)
            continue

        attempted += 1
        source_dir = os.path.join(base_dir, paper.source.replace(" ", "_"))
        filename = f"{_safe_filename(paper.title)}.pdf"
        dest = os.path.join(source_dir, filename)

        if os.path.exists(dest):
            results["downloaded"].append({"title": paper.title, "path": dest, "url": pdf_url})
            continue

        print(f"  다운로드: {paper.title[:60]}...")
        success = download_pdf(pdf_url, dest)

        if success:
            paper.keywords.append(f"pdf:{dest}")  # 경로를 paper에 기록
            results["downloaded"].append({"title": paper.title, "path": dest, "url": pdf_url})
            print(f"    ✓ 저장: {dest}")
        else:
            results["failed"].append({"title": paper.title, "url": pdf_url})
            print(f"    ✗ 실패: {pdf_url[:80]}")

        time.sleep(delay)

    return results


def print_download_summary(results: dict) -> None:
    total = len(results["downloaded"]) + len(results["no_pdf"]) + len(results["failed"])
    print(f"\n{'='*60}")
    print(f"  PDF 다운로드 결과")
    print(f"{'='*60}")
    print(f"  성공:        {len(results['downloaded'])}건")
    print(f"  OA PDF 없음: {len(results['no_pdf'])}건")
    print(f"  다운로드 실패: {len(results['failed'])}건")
    print(f"{'='*60}")
