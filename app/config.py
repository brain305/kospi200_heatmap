"""환경설정 로딩. .env 를 읽어 os.environ 에 채우고(이미 있으면 유지) 상수로 노출."""
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))                      # kospi200-app/app/
PROJECT_DIR = os.path.dirname(APP_DIR)                                    # kospi200-app/


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

# AI 요약 (Google Gemini 무료 티어, 구독자 전용)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
SUMMARY_CACHE_TTL = float(os.getenv("SUMMARY_CACHE_TTL", "10800"))  # 3시간(쿼터 절약). 뉴스는 24h 윈도우
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "10"))            # 일반 구독자 하루 한도
ADMIN_AI_DAILY_LIMIT = int(os.getenv("ADMIN_AI_DAILY_LIMIT", "1000"))  # 관리자 하루 한도
GLOBAL_AI_DAILY_CAP = int(os.getenv("GLOBAL_AI_DAILY_CAP", "2000"))    # 전체 실호출 상한(비용 안전장치)


def ai_daily_limit(user):
    """사용자별 AI 요약 일일 한도. 관리자는 더 큼."""
    return ADMIN_AI_DAILY_LIMIT if (user and user.get("is_admin")) else AI_DAILY_LIMIT

# 호재/악재 분류 (V2.1)
# keyword(기본,무료) | ollama(무료,로컬) | openai(유료)
SENTIMENT_PROVIDER = os.getenv("SENTIMENT_PROVIDER", "keyword")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
# Ollama (로컬 무료). 도커 컨테이너에서 호스트 접근은 host.docker.internal
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# ── V3: 회원/구독 ──
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-insecure-change-me")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")   # 카카오 redirect 기준
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")          # 선택(보안 강화 시)
KAKAO_REDIRECT_PATH = os.getenv("KAKAO_REDIRECT_PATH", "/auth/kakao/callback")

# ── 광고 (쿠팡 파트너스 등) ──
# 광고 스니펫은 app/ad_snippet.html 에 붙여넣기 (gitignore 대상, 커밋 금지)
AD_SNIPPET_PATH = os.getenv("AD_SNIPPET_PATH", os.path.join(APP_DIR, "ad_snippet.html"))
AD_DISCLOSURE = os.getenv(
    "AD_DISCLOSURE",
    "이 사이트는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")

# ── 결제/구독 (Toss Payments, 단건결제로 N일 구독) ──
TOSS_CLIENT_KEY = os.getenv("TOSS_CLIENT_KEY", "")   # test_ck_... / live_ck_...
TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "")   # test_sk_... / live_sk_...
SUBSCRIPTION_PRICE = int(os.getenv("SUBSCRIPTION_PRICE", "4900"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
SUBSCRIPTION_NAME = os.getenv("SUBSCRIPTION_NAME", "KOSPI200 트리맵 구독 30일")

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
