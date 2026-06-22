"""ESG 관련성 필터 — 키워드 기반 점수 분류 (Gemini API 호출 없음).

Gemini 무료 한도(20회/일)를 요약에만 집중 사용하기 위해
키워드 매칭 방식으로 관련성을 판단합니다.
"""

from typing import List, Tuple
from models import Paper

THRESHOLD = 0.3
MAX_OUTPUT = 50

# 핵심 ESG 키워드 (하나라도 있으면 score += 0.35)
TIER1 = {
    "esg", "sustainability", "sustainable development",
    "climate change", "carbon neutral", "carbon neutrality", "net zero",
    "greenhouse gas", "ghg emission", "biodiversity", "renewable energy",
    "carbon emission", "carbon market", "green finance", "tcfd",
    "scope 3", "scope 1", "scope 2", "paris agreement", "carbon pricing",
    "carbon tax", "decarbonization", "just transition", "climate risk",
    "green bond", "esg reporting", "csr", "corporate social responsibility",
    "environmental impact", "climate policy", "carbon footprint",
}

# 관련 키워드 (하나라도 있으면 score += 0.15)
TIER2 = {
    "climate", "carbon", "emission", "renewable", "clean energy",
    "low carbon", "fossil fuel", "ecological", "deforestation",
    "conservation", "ecosystem", "solar energy", "wind energy",
    "energy transition", "green economy", "circular economy",
    "water resource", "air quality", "pollution", "environmental",
    "habitat", "species", "land use", "nature-based", "reforestation",
    "carbon capture", "ccs", "carbon sequestration", "methane",
    "nitrogen oxide", "particulate matter",
}

# 보조 키워드 (score += 0.08)
TIER3 = {
    "recycling", "waste management", "energy efficiency",
    "green building", "sustainable finance", "impact investing",
    "social governance", "stakeholder", "supply chain",
    "lifecycle assessment", "lca", "environmental accounting",
}


def score_paper(paper: Paper) -> float:
    text = f"{paper.title} {paper.abstract or ''}".lower()
    score = 0.0
    for kw in TIER1:
        if kw in text:
            score += 0.35
    for kw in TIER2:
        if kw in text:
            score += 0.15
    for kw in TIER3:
        if kw in text:
            score += 0.08
    return min(1.0, score)


def filter_by_relevance(
    papers: List[Paper],
    threshold: float = THRESHOLD,
    max_output: int = MAX_OUTPUT,
) -> Tuple[List[Paper], List[float]]:
    """키워드 기반 ESG 관련성 필터링 (Gemini API 미사용).

    Returns:
        (filtered_papers, all_scores) — 점수 내림차순, max_output 개 제한
    """
    if not papers:
        return [], []

    scored = [(p, score_paper(p)) for p in papers]
    scored.sort(key=lambda x: x[1], reverse=True)

    filtered = [(p, s) for p, s in scored if s >= threshold][:max_output]
    all_scores = [s for _, s in scored]

    filtered_papers = [p for p, _ in filtered]
    filtered_scores = [s for _, s in filtered]

    avg = sum(filtered_scores) / len(filtered_scores) if filtered_scores else 0
    print(f"  관련성 필터: {len(papers)}건 → {len(filtered_papers)}건 (임계값 {threshold}, 평균점수 {avg:.2f})")

    return filtered_papers, all_scores
