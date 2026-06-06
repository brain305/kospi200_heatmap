"""환경설정 로딩. .env 를 읽어 os.environ 에 채우고(이미 있으면 유지) 상수로 노출."""
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # kospi200-app/


def _load_dotenv():
    envp = os.path.join(PROJECT_DIR, ".env")
    if not os.path.exists(envp):
        return
    for line in open(envp, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# 로컬 기본값은 sqlite (도커/운영은 .env 의 mysql+pymysql://...)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + os.path.join(PROJECT_DIR, "kospi200.db"))

KIS_APPKEY = os.getenv("KIS_APPKEY", "")
KIS_APPSECRET = os.getenv("KIS_APPSECRET", "")
KIS_BASE = os.getenv("KIS_BASE", "https://openapivts.koreainvestment.com:29443")  # 모의투자

KRX_ID = os.getenv("KRX_ID", "")
KRX_PW = os.getenv("KRX_PW", "")

# 네이버 검색 API (V2 뉴스)
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
NEWS_CACHE_TTL = float(os.getenv("NEWS_CACHE_TTL", "1800"))   # 뉴스 캐시(초, 기본 30분)

# 호재/악재 분류 (V2.1)
# keyword(기본,무료) | ollama(무료,로컬) | openai(유료)
SENTIMENT_PROVIDER = os.getenv("SENTIMENT_PROVIDER", "keyword")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
# Ollama (로컬 무료). 도커 컨테이너에서 호스트 접근은 host.docker.internal
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# 실시간 조회 설정
RT_MAX_WORKERS = int(os.getenv("RT_MAX_WORKERS", "4"))
RT_SLEEP_SEC = float(os.getenv("RT_SLEEP_SEC", "0.25"))
RT_CACHE_TTL = float(os.getenv("RT_CACHE_TTL", "10"))   # 실시간 서버 캐시(초)
DF_CACHE_TTL = float(os.getenv("DF_CACHE_TTL", "300"))  # DB 로딩 캐시(초)

TOKEN_CACHE = os.getenv("TOKEN_CACHE", os.path.join(PROJECT_DIR, "data", "kis_token.json"))

# 백업/스케줄
BACKUP_DIR = os.getenv("BACKUP_DIR", "/backups")
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "14"))         # 보관 개수
UPDATE_CRON_HOUR = int(os.getenv("UPDATE_CRON_HOUR", "18"))   # 평일 업데이트 시각(시)
UPDATE_CRON_MIN = int(os.getenv("UPDATE_CRON_MIN", "0"))
BACKUP_CRON_HOUR = int(os.getenv("BACKUP_CRON_HOUR", "18"))
BACKUP_CRON_MIN = int(os.getenv("BACKUP_CRON_MIN", "30"))
