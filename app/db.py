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


# ── 결제 주문 ─────────────────────────────────────────────────
orders = Table(
    "orders", metadata,
    Column("order_id", String(64), primary_key=True),
    Column("user_id", BigInteger, nullable=False),
    Column("amount", BigInteger, nullable=False),
    Column("status", String(20), nullable=False, server_default="pending"),  # pending/paid/failed
    Column("created_at", DateTime, nullable=True),
    Index("idx_orders_user", "user_id"),
)


def create_order(order_id, user_id, amount):
    with get_engine().begin() as conn:
        conn.execute(orders.insert().values(
            order_id=order_id, user_id=user_id, amount=amount,
            status="pending", created_at=dt.datetime.utcnow()))


def get_order(order_id):
    with get_engine().connect() as conn:
        row = conn.execute(select(orders).where(orders.c.order_id == order_id)).mappings().first()
        return dict(row) if row else None


def set_order_status(order_id, status):
    with get_engine().begin() as conn:
        conn.execute(orders.update().where(orders.c.order_id == order_id).values(status=status))


# ── AI 요약 일일 사용량 ───────────────────────────────────────
ai_usage = Table(
    "ai_usage", metadata,
    Column("user_id", BigInteger, nullable=False),
    Column("day", Date, nullable=False),
    Column("count", Integer, nullable=False, server_default="0"),
    PrimaryKeyConstraint("user_id", "day"),
)


def get_ai_usage(user_id, day=None):
    day = day or dt.date.today()
    with get_engine().connect() as conn:
        v = conn.execute(select(ai_usage.c.count).where(
            ai_usage.c.user_id == user_id, ai_usage.c.day == day)).scalar()
        return int(v or 0)


def incr_ai_usage(user_id, day=None):
    """오늘 사용량 +1, 갱신된 값 반환."""
    day = day or dt.date.today()
    with get_engine().begin() as conn:
        cur = conn.execute(select(ai_usage.c.count).where(
            ai_usage.c.user_id == user_id, ai_usage.c.day == day)).scalar()
        if cur is None:
            conn.execute(ai_usage.insert().values(user_id=user_id, day=day, count=1))
            return 1
        conn.execute(ai_usage.update().where(
            ai_usage.c.user_id == user_id, ai_usage.c.day == day).values(count=cur + 1))
        return cur + 1


def extend_subscription(user_id, days):
    """오늘 또는 기존 만료일(미래면) 기준으로 days 만큼 연장. 반환: 새 만료일."""
    user = get_user(user_id)
    today = dt.date.today()
    cur = user.get("subscribed_until") if user else None
    base = cur if (cur and cur >= today) else today
    new_until = base + dt.timedelta(days=days)
    with get_engine().begin() as conn:
        conn.execute(users.update().where(users.c.id == user_id).values(
            is_subscribed=True, subscribed_until=new_until))
    return new_until


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
