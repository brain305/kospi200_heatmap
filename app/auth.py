"""
카카오 OAuth 로그인 + 세션 + 현재 사용자 (V3)

흐름:
  /auth/login            -> 카카오 인증 페이지로 리다이렉트
  /auth/kakao/callback   -> code 로 토큰/프로필 받아 users upsert, 세션에 user_id 저장
  /auth/logout           -> 세션 삭제
  /api/me                -> 로그인/구독 상태 반환 (프런트 게이팅용)

세션은 Starlette SessionMiddleware(서명 쿠키) 사용. KAKAO_REST_API_KEY 없으면
로그인 비활성(프런트는 전부 무료 사용자로 동작).
"""
import urllib.parse

import requests
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

from app import config, db

router = APIRouter()

KAKAO_AUTH = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN = "https://kauth.kakao.com/oauth/token"
KAKAO_ME = "https://kapi.kakao.com/v2/user/me"


def _redirect_uri():
    return config.APP_BASE_URL.rstrip("/") + config.KAKAO_REDIRECT_PATH


def current_user(request: Request):
    uid = request.session.get("user_id")
    return db.get_user(uid) if uid else None


@router.get("/auth/login")
def login():
    if not config.KAKAO_REST_API_KEY:
        return JSONResponse({"error": "kakao_not_configured"}, status_code=503)
    params = {
        "client_id": config.KAKAO_REST_API_KEY,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
    }
    return RedirectResponse(f"{KAKAO_AUTH}?{urllib.parse.urlencode(params)}")


@router.get("/auth/kakao/callback")
def kakao_callback(request: Request, code: str = "", error: str = ""):
    if error or not code:
        return RedirectResponse("/?login=fail")
    data = {
        "grant_type": "authorization_code",
        "client_id": config.KAKAO_REST_API_KEY,
        "redirect_uri": _redirect_uri(),
        "code": code,
    }
    if config.KAKAO_CLIENT_SECRET:
        data["client_secret"] = config.KAKAO_CLIENT_SECRET
    try:
        tok = requests.post(KAKAO_TOKEN, data=data, timeout=10).json()
        if "access_token" not in tok:
            print(f"[auth] 토큰 발급 실패 응답: {tok} (redirect_uri={_redirect_uri()})")
            return RedirectResponse("/?login=fail")
        access = tok["access_token"]
        me = requests.get(KAKAO_ME, headers={"Authorization": f"Bearer {access}"},
                          timeout=10).json()
        uid = me["id"]
        acc = me.get("kakao_account", {}) or {}
        profile = acc.get("profile", {}) or {}
        nickname = profile.get("nickname", "") or f"user{uid}"
        email = acc.get("email", "") or ""
        user = db.upsert_user("kakao", uid, nickname=nickname, email=email)
        request.session["user_id"] = user["id"]
    except Exception as e:
        print(f"[auth] kakao callback 실패: {e}")
        return RedirectResponse("/?login=fail")
    return RedirectResponse("/")


@router.get("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


@router.get("/api/me")
def me(request: Request):
    u = current_user(request)
    if not u:
        body = {"logged_in": False, "kakao_enabled": bool(config.KAKAO_REST_API_KEY)}
    else:
        body = {
            "logged_in": True,
            "nickname": u["nickname"],
            "is_subscribed": db.is_active_subscriber(u),
            "subscribed_until": str(u["subscribed_until"]) if u.get("subscribed_until") else None,
            "is_admin": bool(u["is_admin"]),
        }
    # 로그인 상태가 캐시돼 버튼이 안 바뀌는 문제 방지
    return JSONResponse(body, headers={"Cache-Control": "no-store"})
