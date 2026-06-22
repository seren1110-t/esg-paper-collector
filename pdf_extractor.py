"""PDF 텍스트 추출 모듈.

다운로드된 PDF 파일에서 텍스트를 추출한다.
- 최대 MAX_CHARS 글자로 잘라 Gemini 토큰 한도 대응
- 추출 실패 시 None 반환 (abstract fallback은 호출부에서 처리)
"""

import re
import os
from typing import Optional

MAX_CHARS = 8000  # Gemini 입력 제한 고려


def extract_text(pdf_path: str) -> Optional[str]:
    """PDF 파일에서 텍스트 추출. 실패 시 None."""
    if not os.path.exists(pdf_path):
        return None
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            parts.append(text)
            if sum(len(p) for p in parts) >= MAX_CHARS:
                break
        raw = "\n".join(parts)
        return _clean(raw)[:MAX_CHARS] if raw.strip() else None
    except Exception:
        return None


def _clean(text: str) -> str:
    """불필요한 공백·특수문자 정리."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def find_pdf_path(paper_keywords: list) -> Optional[str]:
    """Paper.keywords에서 'pdf:경로' 태그로 저장된 경로를 찾는다."""
    for kw in paper_keywords:
        if kw.startswith("pdf:"):
            path = kw[4:]
            if os.path.exists(path):
                return path
    return None
