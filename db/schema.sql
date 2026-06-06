-- KOSPI200 일별 데이터 스키마 (MySQL 8)
-- 도커 첫 부팅 시 /docker-entrypoint-initdb.d 로 자동 실행됨.
CREATE TABLE IF NOT EXISTS daily_prices (
  date        DATE         NOT NULL COMMENT '거래일',
  ticker      VARCHAR(6)   NOT NULL COMMENT '종목코드(6자리, 앞 0 보존)',
  name        VARCHAR(40)  NOT NULL COMMENT '종목명',
  close       BIGINT       NOT NULL COMMENT '종가(원)',
  market_cap  BIGINT       NOT NULL COMMENT '시가총액(원)',
  sector      VARCHAR(20)  NOT NULL COMMENT '분야(업종)',
  PRIMARY KEY (ticker, date),
  KEY idx_date (date),
  KEY idx_sector (sector)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- V3: 회원/구독 (없으면 앱 startup 시 SQLAlchemy 가 자동 생성)
CREATE TABLE IF NOT EXISTS users (
  id               BIGINT       NOT NULL AUTO_INCREMENT,
  provider         VARCHAR(20)  NOT NULL,
  provider_uid     VARCHAR(64)  NOT NULL,
  nickname         VARCHAR(60)  NOT NULL DEFAULT '',
  email            VARCHAR(120) NOT NULL DEFAULT '',
  is_subscribed    TINYINT(1)   NOT NULL DEFAULT 0,
  subscribed_until DATE         NULL,
  is_admin         TINYINT(1)   NOT NULL DEFAULT 0,
  created_at       DATETIME     NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_provider_uid (provider, provider_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- AI 요약 열람 기록 (사용자×날짜×종목 단위 1회 과금)
CREATE TABLE IF NOT EXISTS ai_views (
  user_id    BIGINT      NOT NULL,
  day        DATE        NOT NULL,
  name       VARCHAR(40) NOT NULL,
  created_at DATETIME    NULL,
  PRIMARY KEY (user_id, day, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 전역 일일 생성량(실제 Gemini 호출) 비용 안전장치
CREATE TABLE IF NOT EXISTS gen_usage (
  day   DATE   NOT NULL,
  count BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 결제 주문
CREATE TABLE IF NOT EXISTS orders (
  order_id   VARCHAR(64) NOT NULL,
  user_id    BIGINT      NOT NULL,
  amount     BIGINT      NOT NULL,
  status     VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at DATETIME    NULL,
  PRIMARY KEY (order_id),
  KEY idx_orders_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
