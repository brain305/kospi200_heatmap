"""
CSV -> DB 마이그레이션 (Phase 1). app.db 의 스키마/upsert 를 그대로 사용.

[실행] (프로젝트 루트에서)
    python scripts/import_csv_to_db.py --csv ../kospi200_daily_20250606_20260606.csv
    python scripts/import_csv_to_db.py --csv /seed/xxx.csv --reset
"""
import os
import sys
import glob
import argparse
import datetime as dt

import pandas as pd
from sqlalchemy import select, func

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db  # noqa: E402

COLMAP = {"날짜": "date", "티커": "ticker", "종목명": "name",
          "종가": "close", "시가총액": "market_cap", "분야": "sector"}


def find_csv(arg):
    if arg:
        return arg
    for base in (".", "..", "/seed"):
        c = sorted(glob.glob(os.path.join(base, "kospi200_daily_*.csv")))
        if c:
            return c[-1]
    sys.exit("CSV 를 찾을 수 없습니다. --csv 로 지정하세요.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    csv_path = find_csv(args.csv)
    print("CSV:", csv_path)

    df = pd.read_csv(csv_path, dtype={"티커": str}, encoding="utf-8-sig")
    miss = [k for k in COLMAP if k not in df.columns]
    if miss:
        sys.exit(f"CSV 컬럼 누락: {miss}")
    df = df.rename(columns=COLMAP)[list(COLMAP.values())]
    df["ticker"] = df["ticker"].str.zfill(6)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["close"] = df["close"].astype("int64")
    df["market_cap"] = df["market_cap"].astype("int64")
    df = df.drop_duplicates(subset=["ticker", "date"])
    print(f"적재 대상: {len(df):,}행 (종목 {df['ticker'].nunique()} / 날짜 {df['date'].nunique()})")

    db.init_db()
    eng = db.get_engine()
    t = db.daily_prices
    if args.reset:
        with eng.begin() as conn:
            conn.execute(t.delete())
        print("[reset] 기존 데이터 삭제")

    rows = df.to_dict("records")
    n = db.upsert_rows(rows)

    with eng.connect() as conn:
        cnt = conn.execute(select(func.count()).select_from(t)).scalar()
        nt = conn.execute(select(func.count(func.distinct(t.c.ticker)))).scalar()
        nd = conn.execute(select(func.count(func.distinct(t.c.date)))).scalar()
    print(f"\n[검증] 행수 {cnt:,} / 종목 {nt} / 날짜 {nd}  (upsert {n:,})")


if __name__ == "__main__":
    main()
