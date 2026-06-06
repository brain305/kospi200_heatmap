"""
종목 뉴스 수집 (V2) - 네이버 검색 API

규칙:
  - 종목명으로 검색, 최신순(sort=date)
  - 최근 24시간 이내 기사만 유효
  - 그중 최신순 최대 10개 (모자라면 있는 만큼, 없으면 빈 목록)
  - 24시간 넘은 기사는 제외(그 이전 기사는 가져오지 않음)
서버 측 캐시(기본 30분)로 동일 종목 반복 클릭 시 호출 절감.
키(NAVER_CLIENT_ID/SECRET) 없으면 빈 목록 + error 플래그 반환(앱은 깨지지 않음).
"""
import re
import html
import time
import datetime as dt
from urllib.parse import urlparse

import requests

from app import config

KST = dt.timezone(dt.timedelta(hours=9))
_TAG = re.compile(r"<[^>]+>")
_cache = {}   # name -> (ts, items)

NAVER_URL = "https://openapi.naver.com/v1/search/news.json"
MAX_ITEMS = 10
WINDOW_HOURS = 24


def _clean(s):
    return html.unescape(_TAG.sub("", s or "")).strip()


def _source_from(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def parse_items(payload, now=None):
    """네이버 응답 -> 24h 이내 최신순 최대 10개. (테스트 가능하도록 분리)"""
    now = now or dt.datetime.now(KST)
    cutoff = now - dt.timedelta(hours=WINDOW_HOURS)
    rows = []
    for it in payload.get("items", []):
        try:
            pub = dt.datetime.strptime(it["pubDate"], "%a, %d %b %Y %H:%M:%S %z")
        except (KeyError, ValueError):
            continue
        if pub < cutoff:
            continue  # 24시간 초과 -> 무효
        link = it.get("originallink") or it.get("link") or ""
        rows.append({
            "title": _clean(it.get("title")),
            "desc": _clean(it.get("description")),   # 본문 스니펫(요약 입력용)
            "link": link,
            "source": _source_from(link),
            "pub": pub.astimezone(KST).isoformat(),
            "_ts": pub,
        })
    rows.sort(key=lambda x: x["_ts"], reverse=True)  # 최신순
    for r in rows:
        r.pop("_ts", None)
    return rows[:MAX_ITEMS]


def get_news(name):
    if not name:
        return {"items": [], "error": "no_name"}
    if not config.NAVER_CLIENT_ID or not config.NAVER_CLIENT_SECRET:
        return {"items": [], "error": "no_api_key"}

    now = time.time()
    cached = _cache.get(name)
    if cached and now - cached[0] < config.NEWS_CACHE_TTL:
        return {"items": cached[1], "cached": True}

    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }
    params = {"query": name, "display": 50, "sort": "date"}
    try:
        r = requests.get(NAVER_URL, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        items = parse_items(r.json())
    except Exception as e:
        return {"items": [], "error": f"fetch_failed: {e}"}

    # 호재/악재 라벨은 무료에서 제외. 구독자 한정으로 AI(요약 호출 시 함께) 가 부여함.
    _cache[name] = (now, items)
    return {"items": items}
