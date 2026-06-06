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

    # AI 요약: 구독자에겐 기사별 2~3줄 요약, 비구독자에겐 잠금(업셀) 표시
    user = auth.current_user(request)
    is_sub = db.is_active_subscriber(user) if user else False
    summary_locked = False
    overall = None
    out_items = items
    if items and summarize.enabled():
        if is_sub:
            res2 = summarize.get_summaries(name, items)
            overall = res2["overall"] or None
            # 캐시 오염(비구독자 노출) 방지를 위해 복사본에만 summary 부착
            out_items = [{**it, "summary": res2["items"][i]} for i, it in enumerate(items)]
        else:
            summary_locked = True

    payload = {k: v for k, v in result.items() if k != "items"}
    return JSONResponse({"ticker": ticker, "name": name, "items": out_items,
                         "summary": overall, "summary_locked": summary_locked, **payload})


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
