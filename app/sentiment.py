"""
뉴스 호재/악재 분류 (V2.1)

제공자(SENTIMENT_PROVIDER) 선택:
  - "keyword" (기본, 무료): 긍정/부정 키워드 사전으로 제목 점수화. 비용 0, 키 불필요.
  - "ollama"  (무료): 호스트에서 도는 로컬 LLM(Ollama) 호출. 비용 0, 설치 필요.
  - "openai"  (유료): OPENAI_API_KEY 있을 때만. 정확도 최고, 호출 비용 발생.

결과는 news.get_news() 가 뉴스와 함께 캐시하므로 반복 호출되지 않음.
LLM 사용 중 실패하면 자동으로 키워드 방식으로 폴백. (항상 라벨은 나옴)
* 제목 기반 추정이라 참고용.
"""
import json
import re

import requests

from app import config

LABELS = ("호재", "악재", "중립")

# ── 키워드 사전 (무료) ─────────────────────────────────────────
POS = [
    "급등", "상승", "강세", "반등", "회복", "신고가", "최고가", "사상 최대", "최대 실적",
    "호실적", "실적 개선", "흑자", "흑자전환", "흑자 전환", "수주", "수출", "납품", "공급계약",
    "계약 체결", "인수", "합병", "투자 유치", "유치", "수혜", "낙찰", "협력", "맞손", "동맹",
    "목표가 상향", "상향", "매수", "배당", "자사주", "자사주 매입", "신제품", "출시", "승인",
    "허가", "특허", "성장", "확대", "돌파", "호평", "기대", "개선", "역대 최대", "최대 규모",
]
NEG = [
    "급락", "하락", "약세", "폭락", "급감", "감소", "부진", "적자", "적자전환", "적자 전환",
    "손실", "감산", "리콜", "결함", "소송", "피소", "횡령", "배임", "분식", "압수수색", "검찰",
    "벌금", "과징금", "제재", "규제", "철수", "중단", "연기", "지연", "파업", "화재", "사고",
    "목표가 하향", "하향", "매도", "부도", "파산", "감자", "유상증자", "신저가", "최저가",
    "위기", "충격", "쇼크", "우려", "경고", "논란", "의혹", "악재", "부담", "타격", "둔화",
]


def classify_keyword(title):
    t = title or ""
    p = sum(t.count(w) for w in POS)
    n = sum(t.count(w) for w in NEG)
    if p > n:
        return "호재"
    if n > p:
        return "악재"
    return "중립"


# ── LLM 공통 ──────────────────────────────────────────────────
_SYS = ("너는 한국 주식 뉴스 분류기다. 각 제목이 '해당 기업 주가'에 미칠 영향을 "
        "호재/악재/중립 중 하나로 판단한다. 불확실하면 중립. JSON만 출력.")


def _prompt(name, titles):
    lines = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    return (f"기업: {name}\n뉴스 제목:\n{lines}\n\n"
            f'{{"labels":[...]}} 형식 JSON으로만 답하라. labels 길이는 정확히 {len(titles)}.')


def parse_labels(content, n):
    """LLM 응답 -> 길이 n 라벨 리스트."""
    labels = []
    try:
        m = re.search(r"\{.*\}", content, re.S)
        labels = json.loads(m.group(0) if m else content).get("labels", [])
    except Exception:
        labels = re.findall(r"호재|악재|중립", content)
    return [(labels[i] if i < len(labels) and labels[i] in LABELS else "중립") for i in range(n)]


def _openai(name, titles):
    r = requests.post(
        f"{config.OPENAI_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": config.OPENAI_MODEL, "temperature": 0,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "system", "content": _SYS},
                           {"role": "user", "content": _prompt(name, titles)}]},
        timeout=20)
    r.raise_for_status()
    return parse_labels(r.json()["choices"][0]["message"]["content"], len(titles))


def _ollama(name, titles):
    r = requests.post(
        f"{config.OLLAMA_URL}/api/chat",
        json={"model": config.OLLAMA_MODEL, "stream": False, "format": "json",
              "messages": [{"role": "system", "content": _SYS},
                           {"role": "user", "content": _prompt(name, titles)}]},
        timeout=60)
    r.raise_for_status()
    return parse_labels(r.json()["message"]["content"], len(titles))


def classify(items, name=""):
    """items 각 dict 에 'label' 추가. 기본은 무료 키워드, 설정 시 LLM."""
    if not items:
        return items
    titles = [it.get("title", "") for it in items]
    prov = (config.SENTIMENT_PROVIDER or "keyword").lower()
    labels = None
    try:
        if prov == "openai" and config.OPENAI_API_KEY:
            labels = _openai(name, titles)
        elif prov == "ollama":
            labels = _ollama(name, titles)
    except Exception as e:
        print(f"[sentiment] {prov} 실패 -> 키워드 폴백: {e}")
        labels = None
    if not labels:                              # 기본/폴백: 무료 키워드
        labels = [classify_keyword(t) for t in titles]
    for it, lb in zip(items, labels):
        it["label"] = lb
    return items
