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
