"""SQLite 누적 DB — 논문 이력 관리 + 중복 제거."""

import sqlite3
import os
from datetime import datetime
from typing import List
from models import Paper

DB_PATH = os.getenv("DB_PATH", "papers.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """테이블 초기화 (없으면 생성)."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                url         TEXT    UNIQUE NOT NULL,
                title       TEXT    NOT NULL,
                source      TEXT    NOT NULL,
                authors     TEXT,
                abstract    TEXT,
                published_date TEXT,
                collected_at   TEXT NOT NULL,
                summarized  INTEGER DEFAULT 0,
                relevance_score REAL DEFAULT NULL,
                pdf_path    TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS run_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date     TEXT NOT NULL,
                collected    INTEGER DEFAULT 0,
                filtered     INTEGER DEFAULT 0,
                summarized   INTEGER DEFAULT 0,
                failed       INTEGER DEFAULT 0,
                duration_sec INTEGER DEFAULT 0
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_url ON papers(url)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_date ON papers(published_date)")


def filter_new(papers: List[Paper]) -> List[Paper]:
    """이미 DB에 있는 논문 제외 → 신규 논문만 반환."""
    if not papers:
        return []
    urls = [p.url for p in papers if p.url]
    with _conn() as con:
        placeholders = ",".join("?" * len(urls))
        existing = {
            row["url"]
            for row in con.execute(
                f"SELECT url FROM papers WHERE url IN ({placeholders})", urls
            )
        }
    return [p for p in papers if p.url not in existing]


def insert_papers(papers: List[Paper]) -> int:
    """신규 논문 DB 저장. 저장된 건수 반환."""
    if not papers:
        return 0
    now = datetime.utcnow().isoformat()
    rows = [
        (
            p.url,
            p.title,
            p.source,
            "; ".join(p.authors),
            p.abstract,
            p.published_date,
            now,
        )
        for p in papers
        if p.url and p.title
    ]
    with _conn() as con:
        con.executemany(
            """INSERT OR IGNORE INTO papers
               (url, title, source, authors, abstract, published_date, collected_at)
               VALUES (?,?,?,?,?,?,?)""",
            rows,
        )
    return len(rows)


def mark_summarized(url: str, relevance_score: float | None = None, pdf_path: str | None = None) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE papers SET summarized=1, relevance_score=?, pdf_path=? WHERE url=?",
            (relevance_score, pdf_path, url),
        )


def log_run(run_date: str, collected: int, filtered: int, summarized: int,
            failed: int, duration_sec: int) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO run_log (run_date, collected, filtered, summarized, failed, duration_sec)
               VALUES (?,?,?,?,?,?)""",
            (run_date, collected, filtered, summarized, failed, duration_sec),
        )


def stats() -> dict:
    """전체 누적 통계."""
    with _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        summarized = con.execute("SELECT COUNT(*) FROM papers WHERE summarized=1").fetchone()[0]
        by_source = {
            row["source"]: row["cnt"]
            for row in con.execute(
                "SELECT source, COUNT(*) as cnt FROM papers GROUP BY source"
            )
        }
    return {"total": total, "summarized": summarized, "by_source": by_source}
