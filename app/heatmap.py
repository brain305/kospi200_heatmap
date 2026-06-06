"""DB 데이터로 트리맵 페이로드(JSON) 생성. treemap.py 의 검증된 계산 로직 재사용."""
import bisect
import time
import datetime as dt

import numpy as np
import pandas as pd

from app import db, config, realtime

RT_LABEL = "실시간"
CSV_WINDOWS = [("1일", 1), ("1주", 7), ("1개월", 30), ("3개월", 91), ("1년", None), ("YTD", "YTD")]
PERIODS = [RT_LABEL] + [l for l, _ in CSV_WINDOWS]
COLOR_CAP = {RT_LABEL: 5, "1일": 5, "1주": 10, "1개월": 20, "3개월": 40, "1년": 80, "YTD": 60}
COLORSCALE = [[0.0, "#c40000"], [0.25, "#f2433d"], [0.5, "#3a3f4b"],
              [0.75, "#23c265"], [1.0, "#0a9d4a"]]

_cache = {"ts": 0, "builder": None}


def _nearest(sorted_dates, target):
    i = bisect.bisect_right(sorted_dates, target) - 1
    return sorted_dates[max(i, 0)]


def _eok(x):
    v = x / 1e8
    return f"{v/10000:.1f}조원" if v >= 10000 else f"{v:,.0f}억원"


class Builder:
    """DB 스냅샷으로 기간별 수익률을 미리 계산. payload(period)로 프런트용 배열 반환."""

    def __init__(self, df):
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df["sector"] = df["sector"].replace("미분류", "기타")
        self.all_dates = sorted(df["date"].unique())
        self.end = self.all_dates[-1]
        first = self.all_dates[0]

        price = df.set_index(["ticker", "date"])["close"].sort_index()
        cap = df.set_index(["ticker", "date"])["market_cap"].sort_index()
        self.cap = cap
        self.name_of = df.groupby("ticker")["name"].last()
        self.sec_of = df.groupby("ticker")["sector"].last()

        tickers, cap_csv = [], {}
        for tk in df["ticker"].unique():
            try:
                c = cap.loc[(tk, self.end)]; p = price.loc[(tk, self.end)]
            except KeyError:
                continue
            if pd.isna(c) or c <= 0 or pd.isna(p):
                continue
            tickers.append(tk); cap_csv[tk] = float(c)
        self.tickers = tickers
        self.cap_csv = cap_csv
        self.price = price

        # 기간 시작일
        self.start_dates = {}
        for label, spec in CSV_WINDOWS:
            if spec is None:
                self.start_dates[label] = first
            elif spec == "YTD":
                i = bisect.bisect_left(self.all_dates,
                                       np.datetime64(dt.datetime(pd.Timestamp(self.end).year, 1, 1)))
                self.start_dates[label] = self.all_dates[min(i, len(self.all_dates) - 1)]
            else:
                self.start_dates[label] = _nearest(self.all_dates,
                                                   self.end - np.timedelta64(spec, "D"))

        # CSV 기간 수익률
        self.ret = {l: {} for l, _ in CSV_WINDOWS}
        for tk in tickers:
            ser = price.loc[tk]
            p_end = ser.loc[self.end]
            for label, _ in CSV_WINDOWS:
                st = self.start_dates[label]
                self.ret[label][tk] = ((p_end / ser.loc[st] - 1) * 100
                                       if (st in ser.index and st != self.end and ser.loc[st] > 0)
                                       else None)

        self.sectors = sorted(set(self.sec_of[tk] for tk in tickers))

    def _start_cap(self, period):
        """기간 시작일의 종목별 시가총액(가중치용). 없으면 None."""
        if period == RT_LABEL:
            start = self.start_dates["1일"]   # 실시간/1일은 전일 시총으로 가중
        else:
            start = self.start_dates[period]
        w = {}
        for tk in self.tickers:
            try:
                v = self.cap.loc[(tk, start)]
                w[tk] = float(v) if (v and not pd.isna(v)) else None
            except KeyError:
                w[tk] = None
        return w

    def _sector_weighted(self, retmap, weight_cap):
        out = {}
        for s in self.sectors:
            num = den = 0.0
            for tk in self.tickers:
                if self.sec_of[tk] == s and retmap.get(tk) is not None and weight_cap.get(tk):
                    num += weight_cap[tk] * retmap[tk]; den += weight_cap[tk]
            out[s] = (num / den) if den > 0 else 0.0
        return out

    def payload(self, period, rt_ret=None, rt_cap=None):
        # 수익률맵 / 박스크기 결정
        if period == RT_LABEL:
            cap_end = {tk: (rt_cap or {}).get(tk, self.cap_csv[tk]) for tk in self.tickers}
            base = self.ret["1일"]
            retmap = {tk: (rt_ret or {}).get(tk, base[tk]) for tk in self.tickers}
        else:
            cap_end = self.cap_csv
            retmap = self.ret[period]

        sec_cap = {s: 0.0 for s in self.sectors}
        for tk in self.tickers:
            sec_cap[self.sec_of[tk]] += cap_end[tk]
        # 섹터 수익률 집계는 '기간 시작일 시총'으로 가중(상향 편향 방지)
        sec_ret = self._sector_weighted(retmap, self._start_cap(period))

        ROOT = "KOSPI200"
        ids = [ROOT] + [f"sec::{s}" for s in self.sectors] + [f"stk::{tk}" for tk in self.tickers]
        labels = [ROOT] + self.sectors + [self.name_of[tk] for tk in self.tickers]
        parents = [""] + [ROOT] * len(self.sectors) + [f"sec::{self.sec_of[tk]}" for tk in self.tickers]
        values = [sum(sec_cap.values())] + [sec_cap[s] for s in self.sectors] + \
                 [cap_end[tk] for tk in self.tickers]

        colors = [0.0]
        text = [""]
        cdata = [["", ""]]
        for s in self.sectors:
            wr = sec_ret[s]
            colors.append(wr); text.append(f"<b>{s}</b><br>{wr:+.1f}%")
            cdata.append([_eok(sec_cap[s]), f"{wr:+.2f}%"])
        for tk in self.tickers:
            r = retmap.get(tk)
            colors.append(0.0 if r is None else r)
            text.append(f"{self.name_of[tk]}<br>{'N/A' if r is None else f'{r:+.1f}%'}")
            cdata.append([_eok(cap_end[tk]), "N/A" if r is None else f"{r:+.2f}%"])

        cap = COLOR_CAP[period]
        return {
            "period": period, "ids": ids, "labels": labels, "parents": parents,
            "values": values, "colors": colors, "text": text, "customdata": cdata,
            "cmin": -cap, "cmax": cap, "colorscale": COLORSCALE,
            "as_of": str(pd.Timestamp(self.end).date()),
        }


def get_builder():
    """DB 로딩 + 계산을 TTL 캐시."""
    now = time.time()
    if _cache["builder"] is not None and now - _cache["ts"] < config.DF_CACHE_TTL:
        return _cache["builder"]
    df = pd.read_sql_table("daily_prices", db.get_engine())
    b = Builder(df)
    _cache.update(ts=now, builder=b)
    return b


def build(period):
    if period not in PERIODS:
        period = RT_LABEL
    b = get_builder()
    rt_ret = rt_cap = None
    market_open = False
    if period == RT_LABEL:
        rt_ret, rt_cap, ok, err, market_open = realtime.get_realtime_cached(b.tickers)
    out = b.payload(period, rt_ret=rt_ret, rt_cap=rt_cap)
    out["market_open"] = market_open
    out["periods"] = PERIODS
    return out
