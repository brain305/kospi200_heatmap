"""
AI 뉴스 요약 (Google Gemini 무료 티어) - 구독자 전용 기능

- 종목 뉴스 제목들을 투자자 관점 3줄 요약으로 변환.
- 종목별 캐시(기본 30분)로 무료 한도 절약.
- GEMINI_API_KEY 없으면 비활성(None 반환) → 프런트는 요약 미표시.
* 추정/과장 금지 프롬프트. 참고용.
"""
import time

import requests

from app import config

_cache = {}   # name -> (ts, summary)

API_TMPL = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent?key={key}")


def enabled():
    return bool(config.GEMINI_API_KEY)


def _build_prompt(name, titles):
    lines = "\n".join(f"- {t}" for t in titles)
    return (
        f"다음은 '{name}' 관련 최근 뉴스 제목들이다.\n{lines}\n\n"
        "투자자 관점에서 핵심 내용을 한국어 3줄로 요약하라. "
        "각 줄은 간결한 한 문장. 제목에 없는 내용 추측·과장 금지. "
        "불필요한 머리말 없이 요약문만 출력."
    )


def parse_summary(data):
    """Gemini 응답 -> 텍스트. (테스트용 분리)"""
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""


def get_summary(name, items):
    if not enabled() or not items:
        return None
    now = time.time()
    cached = _cache.get(name)
    if cached and now - cached[0] < config.SUMMARY_CACHE_TTL:
        return cached[1]

    titles = [it.get("title", "") for it in items]
    url = API_TMPL.format(model=config.GEMINI_MODEL, key=config.GEMINI_API_KEY)
    try:
        r = requests.post(url, json={
            "contents": [{"parts": [{"text": _build_prompt(name, titles)}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 256},
        }, timeout=20)
        r.raise_for_status()
        summary = parse_summary(r.json()) or None
    except Exception as e:
        print(f"[summarize] 실패: {e}")
        return None

    _cache[name] = (now, summary)
    return summary
