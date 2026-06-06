"""
KOSPI200 1년치 전체 수집 -> DB (Phase 2, 초기 적재용)

기존 collect_kospi200.py 의 DB 버전. CSV 대신 daily_prices 에 upsert.
보통은 import_csv_to_db.py 로 기존 CSV 를 옮기면 충분하고,
이 스크립트는 DB 를 처음부터 새로 채우거나 정기 전체 재적재가 필요할 때 사용.

[실행]
    pip install pykrx pandas sqlalchemy pymysql
    python -m app.collect
"""
import os
import sys
import time
import datetime as dt

from app import config, db

KOSPI200_INDEX = "1028"
SECTOR_INDICES = [
    ("1021", "금융업"), ("1005", "음식료품"), ("1006", "섬유의복"), ("1007", "종이목재"),
    ("1008", "화학"), ("1009", "의약품"), ("1010", "비금속광물"), ("1011", "철강금속"),
    ("1012", "기계"), ("1013", "전기전자"), ("1014", "의료정밀"), ("1015", "운수장비"),
    ("1016", "유통업"), ("1017", "전기가스업"), ("1018", "건설업"), ("1019", "운수창고업"),
    ("1020", "통신업"), ("1026", "서비스업"), ("1024", "증권"), ("1025", "보험"),
]
SLEEP = 0.3


def main():
    db.init_db()
    if not config.KRX_ID or not config.KRX_PW:
        sys.exit("KRX_ID / KRX_PW 가 .env 에 없습니다.")
    os.environ["KRX_ID"] = config.KRX_ID
    os.environ["KRX_PW"] = config.KRX_PW

    from pykrx import stock
    from pykrx.website.comm.auth import login_krx
    if not login_krx(os.environ["KRX_ID"], os.environ["KRX_PW"]):
        sys.exit("[로그인 실패] KRX 자격 증명 확인 필요")
    print("KRX 로그인 성공")

    today = dt.date.today()
    fromd = (today - dt.timedelta(days=365)).strftime("%Y%m%d")
    tod = today.strftime("%Y%m%d")

    idx = stock.get_index_ohlcv_by_date(fromd, tod, KOSPI200_INDEX)
    trading_days = [d.strftime("%Y%m%d") for d in idx.index]
    print(f"거래일 {len(trading_days)}일")

    # 유니버스 + 업종 매핑(최근일 기준)
    universe = set()
    for day in trading_days:
        try:
            m = stock.get_index_portfolio_deposit_file(KOSPI200_INDEX, date=day)
            universe |= set(list(m.index) if hasattr(m, "index") else m)
        except Exception:
            pass
        time.sleep(SLEEP)
    sector_map = {}
    for code, nm in SECTOR_INDICES:
        try:
            m = stock.get_index_portfolio_deposit_file(code, date=trading_days[-1])
            for t in (list(m.index) if hasattr(m, "index") else m):
                sector_map[t] = nm
            time.sleep(SLEEP)
        except Exception:
            pass

    rows = []
    universe = sorted(universe)
    for i, tk in enumerate(universe, 1):
        try:
            name = stock.get_market_ticker_name(tk)
            sector = sector_map.get(tk, "기타")
            ohlcv = stock.get_market_ohlcv_by_date(fromd, tod, tk)
            cap = stock.get_market_cap_by_date(fromd, tod, tk)
            if ohlcv is None or ohlcv.empty:
                continue
            cap_map = {}
            if cap is not None and not cap.empty:
                s = cap["시가총액"]; s.index = cap.index.strftime("%Y-%m-%d")
                cap_map = s.to_dict()
            for d, close in zip(ohlcv.index.strftime("%Y-%m-%d"), ohlcv["종가"].values):
                rows.append({"date": dt.date.fromisoformat(d), "ticker": tk, "name": name,
                             "close": int(close), "market_cap": int(cap_map.get(d, 0)),
                             "sector": sector})
            time.sleep(SLEEP)
        except Exception as e:
            print(f"  [경고] {tk} 실패: {e}")
        if i % 20 == 0:
            print(f"  {i}/{len(universe)} ...")
            db.upsert_rows(rows); rows = []   # 중간 적재

    if rows:
        db.upsert_rows(rows)
    print("완료.")


if __name__ == "__main__":
    main()
