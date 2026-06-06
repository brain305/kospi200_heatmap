"""FastAPI 앱: 트리맵 페이지 + 히트맵 API."""
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db, heatmap

app = FastAPI(title="KOSPI200 Heatmap")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/heatmap")
def api_heatmap(period: str = "실시간"):
    return JSONResponse(heatmap.build(period))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


# /static/* (필요 시 추가 자산)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
