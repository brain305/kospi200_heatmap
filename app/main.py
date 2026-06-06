"""FastAPI 앱: 트리맵 페이지 + 히트맵 API."""
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import db, heatmap, news, auth, config

app = FastAPI(title="KOSPI200 Heatmap")
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET,
                   https_only=False, same_site="lax", max_age=60 * 60 * 24 * 14)
app.include_router(auth.router)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/heatmap")
def api_heatmap(period: str = "실시간"):
    return JSONResponse(heatmap.build(period))


@app.get("/api/news")
def api_news(ticker: str = "", name: str = ""):
    """종목 뉴스(최근 24h, 최신순 최대 10). ticker 또는 name 으로 조회."""
    if ticker and not name:
        try:
            name = str(heatmap.get_builder().name_of.get(ticker) or "")
        except Exception:
            name = ""
    result = news.get_news(name)
    return JSONResponse({"ticker": ticker, "name": name, **result})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


# /static/* (필요 시 추가 자산)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
