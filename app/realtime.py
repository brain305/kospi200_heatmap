"""실시간 시세(KIS Open API) + 토큰 캐시 + 병렬 조회 + 서버 캐시 + 장중 판별."""
import os
import json
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from app import config

_token_lock_ts = 0
_rt_cache = {"ts": 0, "ret": {}, "cap": {}, "ok": 0, "err": 0}


def is_market_open(now=None):
    """KST 평일 09:00~15:30 (공휴일 미판별)."""
    KST = dt.timezone(dt.timedelta(hours=9))
    now = now or dt.datetime.now(KST)
    if now.weekday() >= 5:
        return False
    return dt.time(9, 0) <= now.time() <= dt.time(15, 30)


def _issue_token():
    url = f"{config.KIS_BASE}/oauth2/tokenP"
    body = {"grant_type": "client_credentials",
            "appkey": config.KIS_APPKEY, "appsecret": config.KIS_APPSECRET}
    r = requests.post(url, json=body, timeout=10)
    r.raise_for_status()
    data = r.json()
    token = data["access_token"]
    expires_at = time.time() + int(data.get("expires_in", 82800))
    try:
        with open(config.TOKEN_CACHE, "w") as f:
            json.dump({"access_token": token, "expires_at": expires_at}, f)
    except Exception:
        pass
    return token


def get_token():
    if os.path.exists(config.TOKEN_CACHE):
        try:
            with open(config.TOKEN_CACHE) as f:
                c = json.load(f)
            if time.time() < c["expires_at"] - 300:
                return c["access_token"]
        except Exception:
            pass
    return _issue_token()


def get_price(code, token):
    url = f"{config.KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": config.KIS_APPKEY, "appsecret": config.KIS_APPSECRET,
        "tr_id": "FHKST01010100", "custtype": "P",
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
    r = requests.get(url, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    o = r.json().get("output", {})
    ret = float(o["prdy_ctrt"]) if o.get("prdy_ctrt") not in (None, "") else None
    cap_eok = o.get("hts_avls")
    cap = int(cap_eok) * 100_000_000 if cap_eok not in (None, "") else None  # 억원->원
    return ret, cap


def fetch_realtime(tickers):
    """병렬 조회. 반환: ret{tk:%}, cap{tk:원}, ok, err"""
    if not config.KIS_APPKEY or not config.KIS_APPSECRET:
        return {}, {}, 0, len(tickers)
    try:
        token = get_token()
    except Exception as e:
        print(f"[realtime] 토큰 실패: {e}")
        return {}, {}, 0, len(tickers)

    ret, cap, ok, err = {}, {}, 0, 0

    def worker(tk):
        time.sleep(config.RT_SLEEP_SEC)
        return (tk, *get_price(tk, token))

    with ThreadPoolExecutor(max_workers=config.RT_MAX_WORKERS) as ex:
        futs = {ex.submit(worker, tk): tk for tk in tickers}
        for fut in as_completed(futs):
            try:
                tk, r, c = fut.result()
                if r is not None:
                    ret[tk] = r
                if c is not None:
                    cap[tk] = c
                ok += 1
            except Exception:
                err += 1
    return ret, cap, ok, err


def get_realtime_cached(tickers):
    """서버 측 TTL 캐시. 장중이 아니면 빈 결과(=프런트가 1일로 폴백)."""
    if not is_market_open():
        return {}, {}, 0, 0, False
    now = time.time()
    if now - _rt_cache["ts"] < config.RT_CACHE_TTL and _rt_cache["ok"]:
        return _rt_cache["ret"], _rt_cache["cap"], _rt_cache["ok"], _rt_cache["err"], True
    ret, cap, ok, err = fetch_realtime(tickers)
    _rt_cache.update(ts=now, ret=ret, cap=cap, ok=ok, err=err)
    return ret, cap, ok, err, True
