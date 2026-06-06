"""
일별 데이터 증분 업데이트 -> DB upsert (Phase 2)

기존 update_kospi200.py 의 DB 버전.
- DB 의 마지막 거래일 이후 ~ 오늘까지의 새 거래일을 pykrx 로 받아 upsert.
- 대상 종목: 현재 DB 에 존재하는 유니버스(티커별 최신 name/sector 재사용).
  (신규 편입 종목까지 추적하려면 collect.py 로 전체 재적재 권장)

[실행]
    pip install pykrx pandas sqlalchemy pymysql
    python -m app.update          # .env 의 KRX_ID/KRX_PW, DATABASE_URL 사용
"""
import os
import sys
import time
import datetime as dt

from sqlalchemy import select, func

from app import config, db


def _setup_krx_env():
    if not config.KRX_ID or not config.KRX_PW:
        sys.exit("KRX_ID / KRX_PW 가 .env 에 없습니다.")
    os.environ["KRX_ID"] = config.KRX_ID
    os.environ["KRX_PW"] = config.KRX_PW


def get_universe_and_last_date():
    """DB 에서 (티커->(name,sector)) 와 마지막 거래일 반환."""
    eng = db.get_engine()
    t = db.daily_prices
    with eng.connect() as conn:
        last = conn.execute(select(func.max(t.c.date))).scalar()
        rows = conn.execute(
            select(t.c.ticker, t.c.name, t.c.sector, t.c.date)
            .order_by(t.c.ticker, t.c.date.desc())
        ).fetchall()
    universe = {}
    for tk, name, sector, _d in rows:
        if tk not in universe:               # 첫 등장 = 최신(내림차순 정렬)
            universe[tk] = (name, sector)
    return universe, last


def main():
    db.init_db()
    _setup_krx_env()

    from pykrx import stock  # 환경변수 설정 후 import

    universe, last_date = get_universe_and_last_date()
    if last_date is None:
        sys.exit("DB 가 비어 있습니다. 먼저 import_csv_to_db.py 또는 collect.py 로 적재하세요.")
    print(f"DB 마지막 거래일: {last_date} / 유니버스 {len(universe)} 종목")

    fromd = (last_date + dt.timedelta(days=1)).strftime("%Y%m%d")
    tod = dt.date.today().strftime("%Y%m%d")
    if fromd > tod:
        print("이미 최신입니다.")
        return

    # 새 거래일 목록 (KOSPI200 지수 인덱스로 개장일 판별)
    idx = stock.get_index_ohlcv_by_date(fromd, tod, "1028")
    if idx is None or idx.empty:
        print("추가할 새 거래일이 없습니다(휴장).")
        return
    new_days = [d.strftime("%Y-%m-%d") for d in idx.index]
    print(f"추가 거래일: {len(new_days)} ({new_days[0]} ~ {new_days[-1]})")

    rows = []
    tickers = sorted(universe)
    for i, tk in enumerate(tickers, 1):
        name, sector = universe[tk]
        try:
            ohlcv = stock.get_market_ohlcv_by_date(fromd, tod, tk)
            cap = stock.get_market_cap_by_date(fromd, tod, tk)
            if ohlcv is None or ohlcv.empty:
                continue
            cap_map = {}
            if cap is not None and not cap.empty:
                s = cap["시가총액"]; s.index = cap.index.strftime("%Y-%m-%d")
                cap_map = s.to_dict()
            for d, close in zip(ohlcv.index.strftime("%Y-%m-%d"), ohlcv["종가"].values):
                rows.append({
                    "date": dt.date.fromisoformat(d), "ticker": tk, "name": name,
                    "close": int(close), "market_cap": int(cap_map.get(d, 0)),
                    "sector": sector,
                })
            time.sleep(0.2)
        except Exception as e:
            print(f"  [경고] {tk} 실패: {e}")
        if i % 50 == 0:
            print(f"  {i}/{len(tickers)} ...")

    n = db.upsert_rows(rows)
    print(f"\nupsert 완료: {n:,}행")


if __name__ == "__main__":
    main()
