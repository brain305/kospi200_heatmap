"""FastAPI 앱: 트리맵 페이지 + 히트맵 API."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import db, heatmap, news, auth, billing, summarize, realtime, config

app = FastAPI(title="KOSPI200 Heatmap")
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET,
                   https_only=False, same_site="lax", max_age=60 * 60 * 24 * 14)
app.include_router(auth.router)
app.include_router(billing.router)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/heatmap")
def api_heatmap(period: str = "실시간"):
    return JSONResponse(heatmap.build(period))


@app.get("/api/news")
def api_news(request: Request, ticker: str = "", name: str = ""):
    """종목 뉴스(최근 24h, 최신순 최대 10) + 구독자 전용 AI 요약."""
    if ticker and not name:
        try:
            name = str(heatmap.get_builder().name_of.get(ticker) or "")
        except Exception:
            name = ""
    result = news.get_news(name)
    items = result.get("items") or []

    # AI 요약은 '요약 보기' 버튼(/api/summary)에서만 생성 → 토큰 절약.
    # 여기선 가능 여부/사용량/캐시여부 플래그만 내려줌.
    user = auth.current_user(request)
    is_sub = db.is_active_subscriber(user) if user else False
    summary_available = summary_locked = False
    ai_used = ai_limit = None
    summary_cached = False
    if items and summarize.enabled():
        if is_sub:
            summary_available = True
            ai_limit = config.ai_daily_limit(user)
            ai_used = db.get_ai_usage(user["id"])
            # 현재 캐시된 '요약 버전'에 이미 과금했으면 무료(재열람). 캐시 없거나 신버전이면 과금 예정.
            if summarize.has_cached(name, len(items)):
                gen = int(summarize.cache_ts(name) or 0)
                summary_cached = db.has_charged(user["id"], name, gen)
            else:
                summary_cached = False
        else:
            summary_locked = True

    payload = {k: v for k, v in result.items() if k != "items"}
    return JSONResponse({"ticker": ticker, "name": name, "items": items,
                         "summary_available": summary_available, "summary_locked": summary_locked,
                         "summary_cached": summary_cached,
                         "ai_used": ai_used, "ai_limit": ai_limit, **payload})


@app.get("/api/summary")
def api_summary(request: Request, ticker: str = "", name: str = ""):
    """버튼 클릭 시에만 호출 → Gemini 생성(캐시 히트는 무차감, 일일 한도 적용). 구독자 전용."""
    if ticker and not name:
        try:
            name = str(heatmap.get_builder().name_of.get(ticker) or "")
        except Exception:
            name = ""
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    if not db.is_active_subscriber(user):
        return JSONResponse({"error": "subscribers_only"}, status_code=403)
    if not summarize.enabled():
        return JSONResponse({"error": "disabled"}, status_code=503)

    items = (news.get_news(name).get("items") or [])
    n = len(items)
    ai_limit = config.ai_daily_limit(user)
    if n == 0:
        return JSONResponse({"summary": None, "summaries": [], "labels": [],
                             "ai_used": db.get_ai_usage(user["id"]), "ai_limit": ai_limit})

    # 과금 정책: (사용자×날짜×종목) 단위 1회 차감. 남이 만든 캐시여도 내가 처음 보면 차감,
    # 같은 종목 재열람은 무료. Gemini 실제 호출은 캐시 미스일 때만(우리 비용 절약).
    cached = summarize.has_cached(name, n)
    if cached:
        # 캐시 히트: 이 버전에 이미 과금했으면 무료, 아니면 신버전이라 과금(한도 확인)
        gen = int(summarize.cache_ts(name) or 0)
        already = db.has_charged(user["id"], name, gen)
        if not already and db.get_ai_usage(user["id"]) >= ai_limit:
            return JSONResponse({"limited": True, "ai_used": db.get_ai_usage(user["id"]),
                                 "ai_limit": ai_limit})
        res = summarize.get_summaries(name, items)         # Gemini 미호출
        if not res:
            return JSONResponse({"error": "unavailable", "ai_used": db.get_ai_usage(user["id"]),
                                 "ai_limit": ai_limit}, status_code=503)
        if not already:
            db.add_charge(user["id"], name, gen)           # 신버전 1회 차감
    else:
        # 캐시 미스 → 새 요약 생성(우리 비용 발생) → 무조건 신버전 과금
        if db.get_ai_usage(user["id"]) >= ai_limit:
            return JSONResponse({"limited": True, "ai_used": db.get_ai_usage(user["id"]),
                                 "ai_limit": ai_limit})
        if db.get_global_gen() >= config.GLOBAL_AI_DAILY_CAP:
            return JSONResponse({"error": "busy", "ai_used": db.get_ai_usage(user["id"]),
                                 "ai_limit": ai_limit}, status_code=503)
        res = summarize.get_summaries(name, items)         # Gemini 호출
        if not res:                                        # 실패(429 등) → 과금/집계 안 함
            return JSONResponse({"error": "unavailable", "ai_used": db.get_ai_usage(user["id"]),
                                 "ai_limit": ai_limit}, status_code=503)
        db.incr_global_gen()
        gen = int(summarize.cache_ts(name) or 0)
        db.add_charge(user["id"], name, gen)               # 새 버전 1회 차감
    return JSONResponse({
        "summary": res["overall"] or None, "sentiment": res["sentiment"], "score": res["score"],
        "summaries": res["summaries"], "labels": res["labels"],
        "ai_used": db.get_ai_usage(user["id"]), "ai_limit": ai_limit,
    }, headers={"Cache-Control": "no-store"})


@app.get("/api/ad")
def api_ad():
    """광고 스니펫(쿠팡 파트너스 등). 파일 있으면 enabled. 프런트가 비구독자에게만 렌더."""
    html = ""
    if os.path.exists(config.AD_SNIPPET_PATH):
        try:
            html = open(config.AD_SNIPPET_PATH, encoding="utf-8").read().strip()
        except Exception:
            html = ""
    return JSONResponse(
        {"enabled": bool(html), "html": html, "disclosure": config.AD_DISCLOSURE},
        headers={"Cache-Control": "no-store"})


def _resolve_name(ticker, name=""):
    if name:
        return name
    try:
        return str(heatmap.get_builder().name_of.get(ticker) or "")
    except Exception:
        return ""


@app.get("/api/watchlist")
def api_watchlist_get(request: Request):
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    return JSONResponse(jsonable_encoder({"items": db.get_watch(user["id"])}),
                        headers={"Cache-Control": "no-store"})


@app.post("/api/watchlist")
async def api_watchlist_add(request: Request):
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    body = await request.json()
    ticker = (body.get("ticker") or "").strip()
    if not ticker:
        return JSONResponse({"error": "no_ticker"}, status_code=400)
    # 무료 사용자 관심종목 개수 제한(구독자/관리자/테스트는 무제한)
    privileged = db.is_active_subscriber(user) or user.get("is_admin") or user.get("is_test")
    if not privileged and db.count_watch(user["id"]) >= config.WATCHLIST_FREE_MAX:
        return JSONResponse({"error": "limit", "max": config.WATCHLIST_FREE_MAX}, status_code=403)
    db.add_watch(user["id"], ticker, _resolve_name(ticker, body.get("name", "")))
    return JSONResponse({"ok": True})


@app.delete("/api/watchlist")
def api_watchlist_del(request: Request, ticker: str = ""):
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    db.remove_watch(user["id"], ticker)
    return JSONResponse({"ok": True})


@app.get("/api/watchlist/live")
def api_watchlist_live(request: Request):
    """관심종목 + 현재 등락률(장중=실시간, 장마감=1일 기준)."""
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    items = db.get_watch(user["id"])
    market_open = realtime.is_market_open()
    if not items:
        return JSONResponse({"items": [], "market_open": market_open},
                            headers={"Cache-Control": "no-store"})
    tickers = [it["ticker"] for it in items]
    rt = {}
    if market_open:
        try:
            rt = realtime.get_quotes_cached(tickers)   # 종목단위 30초 캐시
        except Exception:
            rt = {}
    try:
        b = heatmap.get_builder()
    except Exception:
        b = None
    out = []
    for it in items:
        t = it["ticker"]
        pct = rt.get(t)
        if pct is None and b is not None:
            pct = b.ret.get("1일", {}).get(t)
        nm = it["name"] or (str(b.name_of.get(t, "")) if b is not None else "")
        out.append({"ticker": t, "name": nm, "pct": pct})
    return JSONResponse({"items": out, "market_open": market_open},
                        headers={"Cache-Control": "no-store"})


@app.get("/api/alerts")
def api_alerts(request: Request):
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"logged_in": False, "items": [], "unread": 0},
                            headers={"Cache-Control": "no-store"})
    return JSONResponse(jsonable_encoder(
        {"logged_in": True, "items": db.get_alerts(user["id"]),
         "unread": db.count_unread(user["id"])}),
        headers={"Cache-Control": "no-store"})


@app.post("/api/alerts/read")
def api_alerts_read(request: Request):
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    db.mark_alerts_read(user["id"])
    return JSONResponse({"ok": True})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


# /static/* (필요 시 추가 자산)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
