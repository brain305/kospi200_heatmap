"""
구독/관리자 수동 부여 (V3, 결제 전 테스트용)

[목록]
    python scripts/grant_sub.py --list
[구독 부여] (카카오 회원번호 또는 내부 user id)
    python scripts/grant_sub.py --kakao 1234567890 --days 30
    python scripts/grant_sub.py --user 1 --days 30
[관리자 지정 / 구독 해제]
    python scripts/grant_sub.py --user 1 --admin
    python scripts/grant_sub.py --user 1 --revoke

도커에서:
    docker compose run --rm web python scripts/grant_sub.py --list
"""
import os
import sys
import argparse
import datetime as dt

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db  # noqa: E402


def _find(conn, args):
    u = db.users
    if args.user:
        q = select(u).where(u.c.id == int(args.user))
    elif args.kakao:
        q = select(u).where(u.c.provider == "kakao", u.c.provider_uid == str(args.kakao))
    else:
        return None
    return conn.execute(q).mappings().first()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--user")
    ap.add_argument("--kakao")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--admin", action="store_true")
    ap.add_argument("--revoke", action="store_true")
    args = ap.parse_args()

    db.init_db()
    eng = db.get_engine()
    u = db.users

    if args.list:
        with eng.connect() as conn:
            rows = conn.execute(select(u).order_by(u.c.id)).mappings().all()
        if not rows:
            print("(회원 없음)")
        for r in rows:
            print(f"  id={r['id']} kakao={r['provider_uid']} '{r['nickname']}' "
                  f"sub={bool(r['is_subscribed'])} until={r['subscribed_until']} admin={bool(r['is_admin'])}")
        return

    with eng.begin() as conn:
        row = _find(conn, args)
        if not row:
            print("대상 사용자를 찾을 수 없습니다. (--user 또는 --kakao 확인, 먼저 1회 로그인 필요)")
            return
        vals = {}
        if args.revoke:
            vals.update(is_subscribed=False, subscribed_until=None)
        else:
            vals.update(is_subscribed=True,
                        subscribed_until=dt.date.today() + dt.timedelta(days=args.days))
        if args.admin:
            vals["is_admin"] = True
        conn.execute(u.update().where(u.c.id == row["id"]).values(**vals))
        print(f"완료: id={row['id']} '{row['nickname']}' -> {vals}")


if __name__ == "__main__":
    main()
