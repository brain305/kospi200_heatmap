"""
AI 뉴스 요약 (Google Gemini 무료 티어) - 구독자 전용

- 종목 뉴스 '각 기사'를 투자자 관점 2~3문장으로 요약.
- 10개 기사를 한 번의 호출로 배치 요약(JSON) → 무료 한도 절약 + 30분 캐시.
- GEMINI_API_KEY 없으면 비활성(None) → 프런트 요약 미표시.
* 제목/스니펫 기반 참고용. 추측·과장 금지 프롬프트.
"""
import re
import json
import time

import requests

from app import config

_cache = {}   # name -> (ts, [summary, ...])

API_TMPL = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent?key={key}")


def enabled():
    return bool(config.GEMINI_API_KEY)


def _build_prompt(name, items):
    lines = []
    for i, it in enumerate(items, 1):
        t = it.get("title", "")
        d = it.get("desc", "")
        lines.append(f"{i}. 제목: {t}\n   내용: {d}")
    body = "\n".join(lines)
    n = len(items)
    return (
        f"다음은 '{name}' 관련 최근 뉴스 {n}건이다.\n{body}\n\n"
        f"투자자 관점에서 한국어로 분석하라. 제목/내용에 없는 사실 추측·과장 금지.\n"
        f'반드시 JSON 으로만 출력:\n'
        f'{{"overall":"전체 흐름을 3문장으로 요약", '
        f'"summaries":["기사1 2~3문장 요약","기사2 ...", ...]}}\n'
        f"summaries 길이는 정확히 {n}, 입력 순서와 동일하게."
    )


def parse_result(text, n):
    """Gemini 응답 -> {'overall': str, 'items': [str x n]}."""
    overall, out = "", []
    try:
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0) if m else text)
        overall = (data.get("overall") or "").strip()
        out = data.get("summaries", []) or []
    except Exception:
        pass
    items = [(out[i].strip() if i < len(out) and isinstance(out[i], str) else "") for i in range(n)]
    return {"overall": overall, "items": items}


def _gemini_text(prompt):
    url = API_TMPL.format(model=config.GEMINI_MODEL, key=config.GEMINI_API_KEY)
    r = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def get_summaries(name, items):
    """전체+기사별 요약. 반환: {'overall': str, 'items': [str x n]}. 캐시 사용."""
    n = len(items)
    empty = {"overall": "", "items": ["" for _ in range(n)]}
    if not enabled() or n == 0:
        return empty
    now = time.time()
    cached = _cache.get(name)
    if cached and now - cached[0] < config.SUMMARY_CACHE_TTL and len(cached[1]["items"]) == n:
        return cached[1]
    try:
        result = parse_result(_gemini_text(_build_prompt(name, items)), n)
    except Exception as e:
        print(f"[summarize] 실패: {e}")
        return empty
    _cache[name] = (now, result)
    return result
