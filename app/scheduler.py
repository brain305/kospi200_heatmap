"""
스케줄러 (Phase 5)

- 평일(월~금) 지정 시각에 app.update 실행 → DB 증분 갱신
- 매일 지정 시각에 DB 논리 백업(csv.gz) → BACKUP_DIR, 최근 N개만 보관

타임존은 컨테이너 TZ(=Asia/Seoul)를 따른다. (compose/Dockerfile 에서 TZ 설정)

[실행]
    python -m app.scheduler
[수동 백업만]
    python -c "from app.scheduler import backup; backup()"
"""
import os
import glob
import datetime as dt

import pandas as pd
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app import config, db


def run_update():
    print(f"[{dt.datetime.now():%F %T}] update 시작")
    try:
        from app import update
        update.main()
        print("update 완료")
    except SystemExit as e:
        print(f"update 중단: {e}")
    except Exception as e:
        print(f"update 오류: {e}")


def backup():
    """daily_prices 전체를 csv.gz 로 저장하고 오래된 백업 정리."""
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    df = pd.read_sql_table("daily_prices", db.get_engine())
    fn = os.path.join(config.BACKUP_DIR, f"daily_prices_{dt.date.today():%Y%m%d}.csv.gz")
    df.to_csv(fn, index=False, compression="gzip", encoding="utf-8-sig")
    print(f"[{dt.datetime.now():%F %T}] 백업 저장: {fn} ({len(df):,}행)")
    # 보관 정리
    files = sorted(glob.glob(os.path.join(config.BACKUP_DIR, "daily_prices_*.csv.gz")))
    for old in files[:-config.BACKUP_KEEP]:
        try:
            os.remove(old); print(f"  오래된 백업 삭제: {os.path.basename(old)}")
        except OSError:
            pass
    return fn


def main():
    db.init_db()
    sched = BlockingScheduler()
    sched.add_job(run_update, CronTrigger(day_of_week="mon-fri",
                  hour=config.UPDATE_CRON_HOUR, minute=config.UPDATE_CRON_MIN),
                  id="daily_update", misfire_grace_time=3600)
    sched.add_job(backup, CronTrigger(hour=config.BACKUP_CRON_HOUR,
                  minute=config.BACKUP_CRON_MIN),
                  id="daily_backup", misfire_grace_time=3600)
    print("스케줄러 시작:")
    for j in sched.get_jobs():
        print(f"  - {j.id}: {j.trigger}")
    sched.start()


if __name__ == "__main__":
    main()
