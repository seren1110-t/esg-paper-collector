"""Gemini 2.0 Flash 기반 ESG 논문 한국어 요약 모듈 (google-genai SDK)."""

import os
import json
import time
from typing import Optional
from dotenv import load_dotenv
from models import Paper
from pdf_extractor import extract_text, find_pdf_path

load_dotenv()

MODEL_NAME = "gemini-3-flash-preview"
REQUEST_DELAY = 1.0

SYSTEM_PROMPT = """당신은 ESG 컨설팅 전문가입니다.
학술 논문을 읽고 ESG 컨설턴트가 즉시 활용할 수 있는 구조화된 한국어 요약을 작성합니다.
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트나 마크다운 코드블록은 포함하지 마세요."""

USER_PROMPT_TEMPLATE = """다음 논문을 분석하여 JSON 형식으로 한국어 요약을 작성하세요.

[논문 정보]
제목: {title}
저자: {authors}
출처: {source}
발행일: {date}

[내용]
{body}

[출력 형식 - 순수 JSON만 반환, 코드블록 없이]
{{
  "one_liner": "논문의 핵심을 1문장으로 요약 (50자 이내)",
  "background": "연구 배경 및 문제 정의 (3~5문장)",
  "methodology": "연구 방법론 및 데이터 (2~3문장)",
  "key_findings": ["핵심 발견 항목1", "항목2", "항목3"],
  "esg_implications": ["ESG/정책/비즈니스 시사점 항목1", "항목2", "항목3"],
  "limitations": "연구 한계 및 향후 과제 (1~2문장)"
}}"""


def _get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(".env 파일에 GEMINI_API_KEY가 없습니다.")
    from google import genai
    return genai.Client(api_key=api_key)


def _build_body(paper: Paper) -> str:
    """PDF 전문 또는 abstract를 입력 텍스트로 구성."""
    pdf_path = find_pdf_path(paper.keywords)
    if pdf_path:
        full_text = extract_text(pdf_path)
        if full_text:
            return f"[PDF 전문]\n{full_text}"
    if paper.abstract:
        return f"[초록]\n{paper.abstract}"
    return "[내용 없음 — 제목과 메타데이터만으로 요약]"


def _parse_response(text: str) -> dict:
    """응답 텍스트에서 JSON 추출 및 파싱."""
    raw = text.strip()
    # ```json ... ``` 블록 제거
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break
    return json.loads(raw)


def summarize(paper: Paper, client) -> dict:
    """논문 1건 요약. 실패 시 error 키 포함 dict 반환."""
    from google.genai import types

    body = _build_body(paper)
    authors_str = ", ".join(paper.authors[:3])
    if len(paper.authors) > 3:
        authors_str += " 외"

    prompt = USER_PROMPT_TEMPLATE.format(
        title=paper.title,
        authors=authors_str or "미상",
        source=paper.source,
        date=paper.published_date or "미상",
        body=body,
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=2048,
            ),
        )
        raw_text = response.text
        try:
            return _parse_response(raw_text)
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 temperature=0으로 재시도
            retry = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt + "\n\n반드시 순수 JSON만 출력하세요. 설명 없이.",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.0,
                    max_output_tokens=2048,
                ),
            )
            try:
                return _parse_response(retry.text)
            except json.JSONDecodeError:
                return {"raw_response": raw_text, "parse_error": True}
    except Exception as e:
        return {"error": str(e)}


def summarize_papers(
    papers: list[Paper],
    max_summaries: int = 20,
    delay: float = REQUEST_DELAY,
) -> list[dict]:
    """논문 목록을 순차 요약."""
    client = _get_client()
    results = []
    total = min(max_summaries, len(papers))

    for i, paper in enumerate(papers):
        if len(results) >= max_summaries:
            break
        if not paper.title:
            continue

        print(f"  [{len(results)+1}/{total}] {paper.title[:60]}...")
        summary = summarize(paper, client)
        results.append({
            "source": paper.source,
            "title": paper.title,
            "authors": paper.authors[:5],
            "url": paper.url,
            "published_date": paper.published_date,
            "summary": summary,
        })
        time.sleep(delay)

    return results


def save_json(results: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def save_markdown(results: list[dict], path: str, date_str: str) -> None:
    """컨설턴트용 Markdown 브리핑 리포트 생성."""
    lines = [
        f"# ESG 논문 브리핑 — {date_str}",
        f"\n> 총 {len(results)}건 | Gemini 3 Flash 한국어 요약\n",
        "---\n",
    ]

    for i, item in enumerate(results, 1):
        s = item.get("summary") or {}

        if s.get("error"):
            lines.append(f"## {i}. {item['title']}\n\n> 요약 실패: {s['error']}\n\n---\n")
            continue
        if s.get("parse_error"):
            lines.append(f"## {i}. {item['title']}\n\n> JSON 파싱 실패 — 원문 응답 저장됨\n\n---\n")
            continue

        authors_str = ", ".join(item.get("authors", [])[:3])
        if len(item.get("authors", [])) > 3:
            authors_str += " 외"

        lines += [
            f"## {i}. {item['title']}",
            f"\n| 항목 | 내용 |",
            f"|------|------|",
            f"| 출처 | {item['source']} |",
            f"| 발행일 | {item.get('published_date', '-')} |",
            f"| 저자 | {authors_str or '-'} |",
            f"| 링크 | {item['url']} |\n",
            f"### 📌 한 줄 요약",
            f"> {s.get('one_liner', '-')}\n",
            f"### 연구 배경",
            f"{s.get('background', '-')}\n",
            f"### 방법론",
            f"{s.get('methodology', '-')}\n",
            f"### 핵심 발견",
        ]
        for finding in (s.get("key_findings") or []):
            lines.append(f"- {finding}")

        lines += [f"\n### ⭐ ESG/정책 시사점"]
        for impl in (s.get("esg_implications") or []):
            lines.append(f"- {impl}")

        lines += [
            f"\n### 한계 및 향후 과제",
            f"{s.get('limitations', '-')}\n",
            "---\n",
        ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
