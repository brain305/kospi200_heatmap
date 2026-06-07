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
        f"너는 신중하고 비판적인 증권 애널리스트다. 투자자 관점에서 한국어로 분석하라. "
        f"제목/내용에 없는 사실 추측·과장 금지.\n"
        f"[감성 판단 기준 - 보수적으로]\n"
        f"- 호재로 쉽게 평가하지 말 것. 막연한 기대·홍보성·단순 신제품 언급은 '중립'.\n"
        f"- 실적 부진/감소, 주가 하락, 목표가 하향, 감산, 리콜, 소송·제재·규제, "
        f"오너 리스크, 유상증자(희석), 매도·차익실현, 업황 둔화, 불확실성 확대 등 "
        f"부정 신호가 있으면 적극적으로 '악재'로 평가하라.\n"
        f"- 호재와 악재 요소가 섞이면 '중립' 또는 더 비중 큰 쪽으로.\n"
        f"- score: 0~100 정수. 50=중립, 명확한 호재만 60+, 부정 신호가 있으면 50 미만으로 "
        f"분명히 낮춰라(강한 악재는 20 이하).\n"
        f"반드시 JSON 으로만 출력:\n"
        f'{{"overall":"전체 흐름을 3문장으로 요약(긍·부정 균형있게)",'
        f'"sentiment":"호재|악재|중립",'
        f'"score": 0~100 정수,'
        f'"summaries":["기사별 2~3문장 요약", ...],'
        f'"labels":["호재|악재|중립", ...]}}\n'
        f"summaries 와 labels 길이는 정확히 {n}, 입력 순서와 동일하게."
    )


_VALID = ("호재", "악재", "중립")


def parse_result(text, n):
    """Gemini 응답 -> {overall, sentiment, score, summaries[n], labels[n]}."""
    overall, sentiment, score, sums, labs = "", "중립", 50, [], []
    try:
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0) if m else text)
        overall = (data.get("overall") or "").strip()
        sentiment = data.get("sentiment") if data.get("sentiment") in _VALID else "중립"
        try:
            score = max(0, min(100, int(round(float(data.get("score", 50))))))
        except Exception:
            score = 50
        sums = data.get("summaries", []) or []
        labs = data.get("labels", []) or []
    except Exception:
        pass
    summaries = [(sums[i].strip() if i < len(sums) and isinstance(sums[i], str) else "") for i in range(n)]
    labels = [(labs[i] if i < len(labs) and labs[i] in _VALID else "중립") for i in range(n)]
    return {"overall": overall, "sentiment": sentiment, "score": score,
            "summaries": summaries, "labels": labels}


def _gemini_text(prompt):
    url = API_TMPL.format(model=config.GEMINI_MODEL, key=config.GEMINI_API_KEY)
    r = requests.post(url, json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
    }, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def has_cached(name, n):
    """유효 캐시 존재 여부(= Gemini 호출 없이 응답 가능). 한도 차감 판단용."""
    c = _cache.get(name)
    return bool(c and time.time() - c[0] < config.SUMMARY_CACHE_TTL and len(c[1]["summaries"]) == n)


def cache_ts(name):
    """현재 캐시된 요약의 생성 시각(epoch). 없으면 None. 과금 '버전' 식별용."""
    c = _cache.get(name)
    return c[0] if c else None


def get_summaries(name, items):
    """전체요약+종합감성+점수+기사별(요약/라벨). 캐시 사용.
    성공 시 dict, 실패(키없음/429/파싱불가) 시 None → 호출측이 과금하지 않도록."""
    n = len(items)
    if not enabled() or n == 0:
        return None
    now = time.time()
    cached = _cache.get(name)
    if cached and now - cached[0] < config.SUMMARY_CACHE_TTL and len(cached[1]["summaries"]) == n:
        return cached[1]
    try:
        result = parse_result(_gemini_text(_build_prompt(name, items)), n)
    except Exception as e:
        print(f"[summarize] 실패: {e}")
        return None
    # 내용이 전혀 없으면 실패로 간주(캐시·과금 안 함)
    if not result["overall"] and not any(result["summaries"]):
        return None
    _cache[name] = (now, result)
    return result
