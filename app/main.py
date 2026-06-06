"""FastAPI 앱: 트리맵 페이지 + 히트맵 API."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import db, heatmap, news, auth, billing, summarize, config

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
            summary_cached = summarize.has_cached(name, len(items))
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

    if not summarize.has_cached(name, n):       # 캐시 미스 → 한도 확인 후 차감
        if db.get_ai_usage(user["id"]) >= ai_limit:
            return JSONResponse({"limited": True, "ai_used": db.get_ai_usage(user["id"]),
                                 "ai_limit": ai_limit})
        db.incr_ai_usage(user["id"])
    res = summarize.get_summaries(name, items)
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


# /static/* (필요 시 추가 자산)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
