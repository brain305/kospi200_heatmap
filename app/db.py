"""DB 공통 모듈: 엔진, daily_prices 테이블 정의, dialect-aware upsert."""
from sqlalchemy import (create_engine, MetaData, Table, Column, Date, String,
                        BigInteger, PrimaryKeyConstraint, Index)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app import config

_engine = None
metadata = MetaData()

daily_prices = Table(
    "daily_prices", metadata,
    Column("date", Date, nullable=False),
    Column("ticker", String(6), nullable=False),
    Column("name", String(40), nullable=False),
    Column("close", BigInteger, nullable=False),
    Column("market_cap", BigInteger, nullable=False),
    Column("sector", String(20), nullable=False),
    PrimaryKeyConstraint("ticker", "date"),
    Index("idx_date", "date"),
    Index("idx_sector", "sector"),
)

_UPDATE_COLS = ["name", "close", "market_cap", "sector"]


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, future=True)
    return _engine


def init_db():
    """테이블 없으면 생성."""
    metadata.create_all(get_engine())


def upsert_rows(rows, chunk=1000):
    """rows: [{date,ticker,name,close,market_cap,sector}, ...] -> upsert.
    MySQL/SQLite 둘 다 지원. 반환: 처리한 행 수."""
    if not rows:
        return 0
    engine = get_engine()
    dialect = engine.dialect.name
    total = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), chunk):
            batch = rows[i:i + chunk]
            if dialect == "mysql":
                stmt = mysql_insert(daily_prices).values(batch)
                stmt = stmt.on_duplicate_key_update(
                    **{c: stmt.inserted[c] for c in _UPDATE_COLS})
            elif dialect == "sqlite":
                stmt = sqlite_insert(daily_prices).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker", "date"],
                    set_={c: getattr(stmt.excluded, c) for c in _UPDATE_COLS})
            else:
                raise NotImplementedError(f"upsert 미지원 dialect: {dialect}")
            conn.execute(stmt)
            total += len(batch)
    return total
