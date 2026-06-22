"""ESG Paper Collector — daily runner.

Usage:
    python main.py                                  # 수집 1일치, JSON+CSV
    python main.py --days 7                         # 7일치 수집
    python main.py --download --summarize           # PDF + 요약
    python main.py --filter --summarize             # 관련성 필터 후 50건 요약
    python main.py --download --filter --summarize  # 전체 파이프라인
"""

import argparse
import json
import csv
import sys
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from models import Paper

COLLECTORS = {
    "arxiv":            ("collectors.arxiv_collector",           "collect"),
    "semantic_scholar": ("collectors.semantic_scholar_collector", "collect"),
    "openalex":         ("collectors.openalex_collector",        "collect"),
    "pubmed":           ("collectors.pubmed_collector",          "collect"),
    "crossref":         ("collectors.crossref_collector",        "collect"),
}

DEFAULT_SOURCES   = "arxiv,openalex,pubmed"
SEQUENTIAL_SOURCES = {"semantic_scholar"}


def run_collector(name: str, module_path: str, func_name: str, days_back: int) -> tuple[str, List[Paper], str | None]:
    import importlib
    try:
        mod = importlib.import_module(module_path)
        papers = getattr(mod, func_name)(days_back=days_back)
        return name, papers, None
    except Exception as exc:
        return name, [], str(exc)


def collect_all(sources: List[str], days_back: int) -> List[Paper]:
    all_papers: List[Paper] = []
    parallel = {n: COLLECTORS[n] for n in sources if n in COLLECTORS and n not in SEQUENTIAL_SOURCES}
    sequential = {n: COLLECTORS[n] for n in sources if n in COLLECTORS and n in SEQUENTIAL_SOURCES}

    with ThreadPoolExecutor(max_workers=max(1, len(parallel))) as executor:
        futures = {executor.submit(run_collector, n, m, f, days_back): n for n, (m, f) in parallel.items()}
        for future in as_completed(futures):
            name, papers, error = future.result()
            if error:
                print(f"  [ERROR] {name}: {error}")
            else:
                print(f"  [OK]    {name}: {len(papers)}건")
                all_papers.extend(papers)

    for name, (mod, fn) in sequential.items():
        _, papers, error = run_collector(name, mod, fn, days_back)
        if error:
            print(f"  [ERROR] {name}: {error}")
        else:
            print(f"  [OK]    {name}: {len(papers)}건")
            all_papers.extend(papers)

    # 제목 기반 1차 중복 제거
    seen: set = set()
    deduped: List[Paper] = []
    for p in all_papers:
        key = p.title.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(p)
    return deduped


def save_json(papers: List[Paper], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in papers], f, ensure_ascii=False, indent=2)


def save_csv(papers: List[Paper], path: str) -> None:
    if not papers:
        return
    fields = list(papers[0].to_dict().keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in papers:
            row = p.to_dict()
            row["authors"]  = "; ".join(row["authors"])
            row["keywords"] = "; ".join(row["keywords"])
            writer.writerow(row)


def print_summary(papers: List[Paper]) -> None:
    print(f"\n{'='*60}")
    print(f"  수집 완료: 총 {len(papers)}건")
    print(f"{'='*60}")
    by_source: dict = {}
    for p in papers:
        by_source.setdefault(p.source, []).append(p)
    for src, ps in sorted(by_source.items()):
        print(f"  {src:25s}: {len(ps):3d}건")
    print(f"{'='*60}")
    sorted_papers = sorted(papers, key=lambda p: p.published_date or "", reverse=True)
    print("\n[최신 5건 미리보기]")
    for i, p in enumerate(sorted_papers[:5], 1):
        authors_str = ", ".join(p.authors[:3]) + (" 외" if len(p.authors) > 3 else "")
        print(f"\n{i}. [{p.source}] {p.published_date}")
        print(f"   제목: {p.title[:80]}")
        print(f"   저자: {authors_str}")
        print(f"   URL:  {p.url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ESG 논문 자동 수집·요약 파이프라인")
    parser.add_argument("--days",           type=int, default=1)
    parser.add_argument("--output",         choices=["json", "csv", "both"], default="both")
    parser.add_argument("--sources",        default=DEFAULT_SOURCES)
    parser.add_argument("--outdir",         default="output")
    parser.add_argument("--download",       action="store_true", help="PDF 다운로드")
    parser.add_argument("--max-pdfs",       type=int, default=30)
    parser.add_argument("--filter",         action="store_true", help="ESG 관련성 필터링")
    parser.add_argument("--summarize",      action="store_true", help="Gemini 한국어 요약")
    parser.add_argument("--max-summaries",  type=int, default=50)
    parser.add_argument("--notify",         action="store_true", help="이메일+Slack 발송")
    parser.add_argument("--no-db",          action="store_true", help="DB 중복체크 건너뜀 (테스트용)")
    parser.add_argument("--from-json",      default=None,        help="수집 건너뛰고 JSON 파일에서 논문 로드")
    args = parser.parse_args()

    start_time = time.time()
    sources   = [s.strip() for s in args.sources.split(",")]
    date_str  = datetime.now().strftime("%Y%m%d")
    os.makedirs(args.outdir, exist_ok=True)

    # ── DB 초기화 ──────────────────────────────────────────────
    if not args.no_db:
        from db import init_db
        init_db()

    # ── 1. 수집 or JSON 로드 ───────────────────────────────────
    if args.from_json:
        print(f"\nESG 논문 파이프라인 시작 ({date_str}) — JSON 파일 로드 모드")
        print(f"입력: {args.from_json}\n")
        with open(args.from_json, encoding="utf-8") as f:
            raw = json.load(f)
        papers = [Paper(**{k: v for k, v in d.items() if k in Paper.__dataclass_fields__}) for d in raw]
        collected_count = len(papers)
        print(f"  로드: {collected_count}건")
    else:
        print(f"\nESG 논문 파이프라인 시작 ({date_str}, 최근 {args.days}일)")
        print(f"소스: {', '.join(sources)}\n")
        papers = collect_all(sources, days_back=args.days)
        collected_count = len(papers)
        print_summary(papers)

    # ── 2. DB 중복 제거 (from-json 모드에서는 collect job에서 이미 처리됨) ──
    if not args.no_db and not args.from_json and papers:
        from db import filter_new, insert_papers
        papers = filter_new(papers)
        inserted = insert_papers(papers)
        print(f"\n[DB] 신규 논문: {len(papers)}건 (중복 제외 후) / 저장: {inserted}건")

    # ── 3. JSON / CSV 저장 ─────────────────────────────────────
    if args.output in ("json", "both"):
        path = os.path.join(args.outdir, f"esg_papers_{date_str}.json")
        save_json(papers, path)
        print(f"저장: {path}")
    if args.output in ("csv", "both"):
        path = os.path.join(args.outdir, f"esg_papers_{date_str}.csv")
        save_csv(papers, path)
        print(f"저장: {path}")

    # ── 4. PDF 다운로드 ────────────────────────────────────────
    if args.download and papers:
        from downloader import download_papers, print_download_summary
        pdf_dir = os.path.join(args.outdir, f"pdfs_{date_str}")
        print(f"\nPDF 다운로드 → {pdf_dir}")
        dl_results = download_papers(papers, base_dir=pdf_dir, max_papers=args.max_pdfs)
        print_download_summary(dl_results)
        if args.output in ("json", "both"):
            save_json(papers, os.path.join(args.outdir, f"esg_papers_{date_str}.json"))

    # ── 5. ESG 관련성 필터링 ───────────────────────────────────
    papers_to_summarize = papers
    all_scores: List[float] = []
    if args.filter and papers:
        from relevance_filter import filter_by_relevance
        print(f"\n관련성 필터링 ({len(papers)}건 → 최대 {args.max_summaries}건)")
        papers_to_summarize, all_scores = filter_by_relevance(
            papers, threshold=0.6, max_output=args.max_summaries
        )

    filtered_count = len(papers_to_summarize)

    # ── 6. AI 요약 ─────────────────────────────────────────────
    sum_results: List[dict] = []
    if args.summarize and papers_to_summarize:
        from summarizer import summarize_papers, save_json as save_sum_json, save_markdown
        limit = args.max_summaries if not args.filter else len(papers_to_summarize)
        print(f"\nGemini 요약 ({limit}건) ...")
        sum_results = summarize_papers(papers_to_summarize, max_summaries=limit)

        sum_json_path = os.path.join(args.outdir, f"summary_{date_str}.json")
        sum_md_path   = os.path.join(args.outdir, f"summary_{date_str}.md")
        save_sum_json(sum_results, sum_json_path)
        save_markdown(sum_results, sum_md_path, date_str)

        success = sum(1 for r in sum_results if not (r.get("summary") or {}).get("error"))
        print(f"\n요약 완료: {success}/{len(sum_results)}건")
        print(f"저장: {sum_json_path}")
        print(f"저장: {sum_md_path}")

        # DB 요약 완료 표시
        if not args.no_db:
            from db import mark_summarized
            for item in sum_results:
                mark_summarized(item["url"])

    # ── 7. 알림 발송 ───────────────────────────────────────────
    if args.notify and sum_results:
        from notifier import notify_all
        stats = {
            "collected":  collected_count,
            "filtered":   filtered_count,
            "summarized": len(sum_results),
        }
        print("\n알림 발송 중 ...")
        notify_all(sum_results, date_str, stats)

    # ── 8. 실행 로그 ───────────────────────────────────────────
    duration = int(time.time() - start_time)
    if not args.no_db:
        from db import log_run
        failed = len(sum_results) - sum(
            1 for r in sum_results if not (r.get("summary") or {}).get("error")
        ) if sum_results else 0
        log_run(date_str, collected_count, filtered_count, len(sum_results), failed, duration)

    print(f"\n완료 ({duration}초 소요)\n")


if __name__ == "__main__":
    main()
