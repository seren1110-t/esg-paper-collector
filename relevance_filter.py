"""ESG 관련성 필터 — Gemini 3 Flash로 0.0~1.0 점수 분류.

150건 수집 → 0.6 이상만 선별 → 약 50~70건으로 압축
배치 처리로 API 호출 최소화 (5건씩 묶어서 호출)
"""

import os
import json
import time
from typing import List
from dotenv import load_dotenv
from models import Paper

load_dotenv()

MODEL_NAME = "gemini-3-flash-preview"
THRESHOLD = 0.6
BATCH_SIZE = 5
BATCH_DELAY = 1.0

SYSTEM_PROMPT = """당신은 ESG(환경·사회·지배구조) 전문 분류 시스템입니다.
논문 제목과 초록을 보고 ESG/기후/탄소중립/환경 주제와의 관련성 점수를 0.0~1.0으로 평가합니다.
반드시 JSON 배열만 반환하세요."""

BATCH_PROMPT = """아래 논문 목록의 ESG 관련성을 평가하세요.

평가 기준:
- 1.0: ESG/기후변화/탄소중립/재생에너지/생물다양성이 핵심 주제
- 0.7~0.9: 환경·지속가능성·기업사회책임이 주요 요소
- 0.4~0.6: 간접적으로 관련 (에너지, 도시, 생태계 등)
- 0.0~0.3: 무관 (순수 물리학, 의학, 컴퓨터과학 등)

논문 목록:
{papers_json}

출력 형식 (JSON 배열만, 설명 없이):
[
  {{"idx": 0, "score": 0.9, "reason": "탄소배출 직접 분석"}},
  {{"idx": 1, "score": 0.2, "reason": "핵물리학, ESG 무관"}}
]"""


def _get_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 없음")
    from google import genai
    return genai.Client(api_key=api_key)


def _score_batch(batch: List[Paper], client) -> List[float]:
    """배치 단위 점수 반환. 실패 시 기본값 0.5 반환."""
    from google.genai import types

    papers_input = [
        {"idx": i, "title": p.title, "abstract": (p.abstract or "")[:300]}
        for i, p in enumerate(batch)
    ]
    prompt = BATCH_PROMPT.format(papers_json=json.dumps(papers_input, ensure_ascii=False))

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.0,
                max_output_tokens=512,
            ),
        )
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        results = json.loads(raw.strip())
        scores = [0.5] * len(batch)
        for r in results:
            idx = r.get("idx", -1)
            if 0 <= idx < len(batch):
                scores[idx] = float(r.get("score", 0.5))
        return scores
    except Exception as e:
        print(f"    [WARN] 관련성 배치 실패: {e} → 기본값 0.7 적용")
        return [0.7] * len(batch)  # 실패 시 통과시키는 방향으로 기본값 설정


def filter_by_relevance(
    papers: List[Paper],
    threshold: float = THRESHOLD,
    max_output: int = 50,
) -> tuple[List[Paper], List[float]]:
    """
    ESG 관련성 기준으로 필터링.

    Returns:
        (filtered_papers, all_scores)  — 점수 내림차순 정렬, max_output 개 제한
    """
    if not papers:
        return [], []

    client = _get_client()
    all_scores: List[float] = []

    for i in range(0, len(papers), BATCH_SIZE):
        batch = papers[i: i + BATCH_SIZE]
        scores = _score_batch(batch, client)
        all_scores.extend(scores)
        if i + BATCH_SIZE < len(papers):
            time.sleep(BATCH_DELAY)

    # 점수 붙여서 정렬
    scored = sorted(
        zip(papers, all_scores),
        key=lambda x: x[1],
        reverse=True,
    )

    filtered = [
        (p, s) for p, s in scored
        if s >= threshold
    ][:max_output]

    filtered_papers = [p for p, _ in filtered]
    filtered_scores = [s for _, s in filtered]

    avg = sum(filtered_scores) / len(filtered_scores) if filtered_scores else 0
    print(f"  관련성 필터: {len(papers)}건 → {len(filtered_papers)}건 (임계값 {threshold}, 평균점수 {avg:.2f})")

    return filtered_papers, all_scores
