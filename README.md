# KOSPI200 시가총액 트리맵 (Docker)

코스피200 종목을 시가총액 크기 박스로, 등락률로 색칠한 Finviz 스타일 히트맵.
MySQL + FastAPI + Plotly.js, Docker Compose 로 구동.

## 구조
```
kospi200-app/
├─ docker-compose.yml      # db(MySQL) + web(FastAPI)
├─ Dockerfile              # web 이미지
├─ requirements.txt
├─ .env.example            # 시크릿 템플릿 (.env 는 커밋 금지)
├─ db/schema.sql           # 테이블 DDL (도커 초기화 시 자동 적용)
├─ scripts/
│  └─ import_csv_to_db.py  # Phase1: 기존 CSV -> DB 이관
├─ seed/                   # 초기 적재용 CSV 두는 곳(선택)
├─ backups/                # 자동 백업 csv.gz 출력
└─ app/
   ├─ config.py            # .env 로딩
   ├─ db.py                # 엔진/테이블/upsert
   ├─ collect.py           # Phase2: 1년치 전체 수집 -> DB
   ├─ update.py            # Phase2: 증분 업데이트 -> DB upsert
   ├─ realtime.py          # Phase3: KIS 실시간 + 캐시 + 장중판별
   ├─ heatmap.py           # Phase3: 기간 수익률 계산 -> 트리맵 페이로드
   ├─ main.py              # FastAPI (/ , /api/heatmap)
   ├─ scheduler.py         # Phase5: 자동 업데이트 + 백업
   └─ static/index.html    # 프런트(다크 트리맵, 탭, 장중 자동갱신)
```

## 빠른 시작 (맥미니/맥북)
```bash
cp .env.example .env          # 값 채우기 (DB 비번 / KIS / KRX)
docker compose up -d db       # MySQL 기동

# 데이터 적재 (둘 중 하나)
#  A) 기존 CSV 이관: seed/ 에 csv 복사 후
docker compose run --rm web python scripts/import_csv_to_db.py --csv /seed/kospi200_daily_20250606_20260606.csv
#  B) 새로 수집(KRX 로그인 필요)
docker compose run --rm web python -m app.collect

docker compose up -d web      # 서버 기동
# http://<맥미니IP>:8000
```

## 일별 업데이트
수동:
```bash
docker compose run --rm web python -m app.update   # DB 마지막일 이후만 upsert
```

### 자동화 (Phase 5 · scheduler 서비스)
`docker compose up -d` 하면 `scheduler` 컨테이너가 함께 떠서:
- **평일 18:00 (KST)** `app.update` 자동 실행 → DB 증분 갱신
- **매일 18:30** DB 논리 백업(`backups/daily_prices_YYYYMMDD.csv.gz`), 최근 14개 보관

시각은 `.env` 로 조절: `UPDATE_CRON_HOUR/MIN`, `BACKUP_CRON_HOUR/MIN`, `BACKUP_KEEP`.
(호스트 cron 을 따로 쓰고 싶으면 scheduler 서비스를 빼고 아래처럼:)
```
0 18 * * 1-5 cd /path/kospi200-app && docker compose run --rm web python -m app.update
```

## 백업 / 복원
- 자동 백업: `backups/daily_prices_*.csv.gz` (scheduler)
- 수동 백업(논리, csv.gz):
```bash
docker compose run --rm scheduler python -c "from app.scheduler import backup; backup()"
```
- 복원(csv.gz → DB):
```bash
gunzip -c backups/daily_prices_YYYYMMDD.csv.gz > seed/restore.csv
docker compose run --rm web python scripts/import_csv_to_db.py --csv /seed/restore.csv --reset
```
- 정통 SQL 덤프(원하면, db 컨테이너 내부의 mysqldump 사용 → 버전 호환 OK):
```bash
docker compose exec db sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" kospi200' > dump.sql
```

## 외부 접속 (Tailscale, 선택)
가장 쉬운 방법은 맥미니 호스트에 Tailscale 설치:
1. 맥미니에 [Tailscale](https://tailscale.com/) 설치·로그인
2. 같은 Tailnet 의 기기에서 `http://<맥미니-tailscale-IP>:8000` 접속
3. (선택) HTTPS 로 노출: `tailscale serve https / http://localhost:8000`

LAN 전용이면 그냥 `http://<맥미니-LAN-IP>:8000`. 공유기 포트포워딩으로 인터넷 직접 노출은 비권장(시크릿/시세 비용 보호).

## 탭
실시간 · 1일 · 1주 · 1개월 · 3개월 · 1년 · YTD
- **1일**: DB 최근 2거래일 종가 등락률(고정)
- **실시간**: 장중에만 KIS 현재가 vs 전일가. 서버가 10초 캐시 → 다중 접속해도 200콜은 10초당 1회. 장 마감/주말엔 1일과 동일.

## 주의
- `.env` 의 KIS/KRX 키는 절대 커밋 금지. 노출됐던 키는 재발급.
- DB 데이터는 깃에 안 들어감 → 맥미니에선 재적재(또는 mysqldump 복원).
- 외부 접속은 Tailscale 권장.
```
mysqldump -h127.0.0.1 -ukospi -p kospi200 daily_prices > dump.sql   # 백업
```

## GitHub 업로드
`.env`/데이터/백업은 `.gitignore` 로 제외됨. 키 노출 없는지 확인 후:
```bash
cd kospi200-app
git init
git add .
git status                      # .env, *.csv, backups/*.gz 가 안 보이는지 확인!
git commit -m "KOSPI200 heatmap: MySQL + FastAPI + scheduler (Docker)"
git branch -M main
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```
맥미니에서:
```bash
git clone https://github.com/<USER>/<REPO>.git && cd <REPO>
cp .env.example .env            # 값 채우기 (재발급한 키)
docker compose up -d db
# seed/ 에 CSV 넣고 이관, 또는 app.collect 로 수집
docker compose run --rm web python scripts/import_csv_to_db.py --csv /seed/<csv>
docker compose up -d            # web + scheduler 기동
```

> ⚠️ 보안 체크: 커밋 전 `git grep -i appsecret` / `git grep -i KRX_PW` 로 키가 코드에 남아있지 않은지 확인하세요. 기존 `realtime_price.py`·`collect_kospi200.py`(상위 폴더의 원본)는 이 레포에 포함하지 마세요.
