"""DB 공통 모듈: 엔진, daily_prices 테이블 정의, dialect-aware upsert."""
import datetime as dt

from sqlalchemy import (create_engine, MetaData, Table, Column, Date, DateTime,
                        String, Boolean, BigInteger, Integer, PrimaryKeyConstraint,
                        UniqueConstraint, Index, select)
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

# ── V3: 회원 ─────────────────────────────────────────────────
users = Table(
    "users", metadata,
    # MySQL=BIGINT AUTO_INCREMENT, SQLite=INTEGER(rowid 자동증가)
    Column("id", BigInteger().with_variant(Integer, "sqlite"),
           primary_key=True, autoincrement=True),
    Column("provider", String(20), nullable=False),       # 'kakao'
    Column("provider_uid", String(64), nullable=False),   # 카카오 회원번호
    Column("nickname", String(60), nullable=False, server_default=""),
    Column("email", String(120), nullable=False, server_default=""),
    Column("is_subscribed", Boolean, nullable=False, server_default="0"),
    Column("subscribed_until", Date, nullable=True),
    Column("is_admin", Boolean, nullable=False, server_default="0"),
    Column("created_at", DateTime, nullable=True),
    UniqueConstraint("provider", "provider_uid", name="uq_provider_uid"),
    Index("idx_provider_uid", "provider", "provider_uid"),
)


def upsert_user(provider, provider_uid, nickname="", email=""):
    """소셜 로그인 사용자 upsert. 반환: user row(dict)."""
    eng = get_engine()
    with eng.begin() as conn:
        row = conn.execute(select(users).where(
            users.c.provider == provider, users.c.provider_uid == str(provider_uid))).mappings().first()
        if row:
            conn.execute(users.update().where(users.c.id == row["id"]).values(
                nickname=nickname or row["nickname"], email=email or row["email"]))
            return dict(row)
        res = conn.execute(users.insert().values(
            provider=provider, provider_uid=str(provider_uid),
            nickname=nickname, email=email, is_subscribed=False, is_admin=False,
            created_at=dt.datetime.utcnow()))
        uid = res.inserted_primary_key[0]
        return dict(conn.execute(select(users).where(users.c.id == uid)).mappings().first())


def get_user(user_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).mappings().first()
        return dict(row) if row else None


def is_active_subscriber(user):
    """구독 활성 여부: is_subscribed AND (만료일 없음 or 오늘 이후)."""
    if not user or not user.get("is_subscribed"):
        return False
    until = user.get("subscribed_until")
    return until is None or until >= dt.date.today()


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
