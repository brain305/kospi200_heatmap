"""DB 공통 모듈: 엔진, daily_prices 테이블 정의, dialect-aware upsert."""
import datetime as dt

from sqlalchemy import (create_engine, MetaData, Table, Column, Date, DateTime,
                        String, Boolean, BigInteger, Integer, PrimaryKeyConstraint,
                        UniqueConstraint, Index, select, func, inspect, text)
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
    Column("is_test", Boolean, nullable=False, server_default="0"),
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


# ── AI 요약 열람 기록 (사용자×날짜×종목 단위 1회 과금) ──────────
ai_views = Table(
    "ai_views", metadata,
    Column("user_id", BigInteger, nullable=False),
    Column("day", Date, nullable=False),
    Column("name", String(40), nullable=False),
    Column("created_at", DateTime, nullable=True),
    PrimaryKeyConstraint("user_id", "day", "name"),
)


def get_ai_usage(user_id, day=None):
    """오늘 차감된 종목 수(=요약 열람한 고유 종목 수)."""
    day = day or dt.date.today()
    with get_engine().connect() as conn:
        return int(conn.execute(
            select(func.count()).select_from(ai_views).where(
                ai_views.c.user_id == user_id, ai_views.c.day == day)).scalar() or 0)


def has_viewed(user_id, name, day=None):
    """오늘 이 종목을 이미 차감했는지(재열람은 무료)."""
    day = day or dt.date.today()
    with get_engine().connect() as conn:
        return conn.execute(select(ai_views.c.name).where(
            ai_views.c.user_id == user_id, ai_views.c.day == day,
            ai_views.c.name == name)).first() is not None


def add_view(user_id, name, day=None):
    """차감 기록 추가. 새로 차감되면 True, 이미 있으면 False."""
    day = day or dt.date.today()
    with get_engine().begin() as conn:
        exists = conn.execute(select(ai_views.c.name).where(
            ai_views.c.user_id == user_id, ai_views.c.day == day,
            ai_views.c.name == name)).first()
        if exists:
            return False
        conn.execute(ai_views.insert().values(
            user_id=user_id, day=day, name=name, created_at=dt.datetime.utcnow()))
        return True


# ── 전역 일일 생성량(실제 Gemini 호출) — 비용 안전장치 ─────────
gen_usage = Table(
    "gen_usage", metadata,
    Column("day", Date, nullable=False),
    Column("count", BigInteger, nullable=False, server_default="0"),
    PrimaryKeyConstraint("day"),
)


def get_global_gen(day=None):
    day = day or dt.date.today()
    with get_engine().connect() as conn:
        return int(conn.execute(select(gen_usage.c.count).where(
            gen_usage.c.day == day)).scalar() or 0)


def incr_global_gen(day=None):
    day = day or dt.date.today()
    with get_engine().begin() as conn:
        cur = conn.execute(select(gen_usage.c.count).where(gen_usage.c.day == day)).scalar()
        if cur is None:
            conn.execute(gen_usage.insert().values(day=day, count=1))
            return 1
        conn.execute(gen_usage.update().where(gen_usage.c.day == day).values(count=cur + 1))
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


def _ensure_column(conn, table, col, ddl_mysql, ddl_sqlite):
    """기존 테이블에 컬럼이 없으면 추가(간이 마이그레이션)."""
    cols = [c["name"] for c in inspect(conn).get_columns(table)]
    if col in cols:
        return
    ddl = ddl_sqlite if conn.engine.dialect.name == "sqlite" else ddl_mysql
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def init_db():
    """테이블 없으면 생성 + 누락 컬럼 보강."""
    eng = get_engine()
    metadata.create_all(eng)
    with eng.begin() as conn:
        _ensure_column(conn, "users", "is_test",
                       "is_test TINYINT(1) NOT NULL DEFAULT 0",
                       "is_test INTEGER NOT NULL DEFAULT 0")


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
