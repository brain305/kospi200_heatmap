"""
결제/구독 (Toss Payments, 단건결제로 30일 구독)

흐름:
  1) 프런트: GET /api/billing/config 로 clientKey/금액 받기
  2) 프런트: POST /api/billing/checkout 로 주문 생성(서버가 orderId·금액 저장)
  3) 프런트: Toss SDK requestPayment() 호출 → 성공 시 successUrl 로 리다이렉트
  4) 서버: GET /billing/success 에서 Toss 승인 API 호출 → 검증 후 구독 30일 부여

테스트 키(test_ck_/test_sk_)면 실제 청구 없이 플로우 검증 가능.
TOSS 키 없으면 결제 비활성(프런트에서 안내).
"""
import uuid
import base64

import requests
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse

from app import config, db, auth

router = APIRouter()

TOSS_CONFIRM = "https://api.tosspayments.com/v1/payments/confirm"


def _enabled():
    return bool(config.TOSS_CLIENT_KEY and config.TOSS_SECRET_KEY)


def confirm_payment(payment_key, order_id, amount):
    """Toss 결제 승인. 성공 시 True. (테스트에서 monkeypatch 가능하도록 분리)"""
    auth_h = base64.b64encode((config.TOSS_SECRET_KEY + ":").encode()).decode()
    r = requests.post(TOSS_CONFIRM,
                      headers={"Authorization": f"Basic {auth_h}",
                               "Content-Type": "application/json"},
                      json={"paymentKey": payment_key, "orderId": order_id, "amount": amount},
                      timeout=15)
    data = r.json()
    return r.status_code == 200 and data.get("status") == "DONE"


@router.get("/api/billing/config")
def billing_config():
    return JSONResponse({
        "enabled": _enabled(),
        "clientKey": config.TOSS_CLIENT_KEY,
        "amount": config.SUBSCRIPTION_PRICE,
        "orderName": config.SUBSCRIPTION_NAME,
        "days": config.SUBSCRIPTION_DAYS,
    }, headers={"Cache-Control": "no-store"})


@router.post("/api/billing/checkout")
def checkout(request: Request):
    user = auth.current_user(request)
    if not user:
        return JSONResponse({"error": "login_required"}, status_code=401)
    if not _enabled():
        return JSONResponse({"error": "billing_disabled"}, status_code=503)
    order_id = "sub_" + uuid.uuid4().hex
    amount = config.SUBSCRIPTION_PRICE
    db.create_order(order_id, user["id"], amount)
    base = config.APP_BASE_URL.rstrip("/")
    return JSONResponse({
        "clientKey": config.TOSS_CLIENT_KEY,
        "orderId": order_id,
        "amount": amount,
        "orderName": config.SUBSCRIPTION_NAME,
        "customerName": user["nickname"] or "회원",
        "successUrl": base + "/billing/success",
        "failUrl": base + "/billing/fail",
    })


@router.get("/billing/success")
def billing_success(request: Request, paymentKey: str = "", orderId: str = "", amount: int = 0):
    order = db.get_order(orderId)
    # 위변조 방지: 주문 존재·미처리·금액 일치 확인
    if not order or order["status"] != "pending" or int(order["amount"]) != int(amount):
        return RedirectResponse("/?sub=fail")
    try:
        ok = confirm_payment(paymentKey, orderId, amount)
    except Exception as e:
        print(f"[billing] 승인 오류: {e}")
        ok = False
    if not ok:
        db.set_order_status(orderId, "failed")
        return RedirectResponse("/?sub=fail")
    db.set_order_status(orderId, "paid")
    db.extend_subscription(order["user_id"], config.SUBSCRIPTION_DAYS)
    return RedirectResponse("/?sub=success")


@router.get("/billing/fail")
def billing_fail(request: Request, code: str = "", message: str = ""):
    print(f"[billing] 실패: {code} {message}")
    return RedirectResponse("/?sub=fail")
