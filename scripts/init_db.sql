-- PostGIS 확장
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- places
-- ============================================================
CREATE TABLE IF NOT EXISTS places (
  place_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            VARCHAR(200) NOT NULL,
  category        VARCHAR(50),
  sub_category    VARCHAR(100),
  address         TEXT,
  district        VARCHAR(50),
  geom            GEOMETRY(Point, 4326),
  phone           VARCHAR(20),
  google_place_id VARCHAR(100),
  booking_url     TEXT,
  raw_data        JSONB,
  source          VARCHAR(50),
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- 중복 방지: 같은 소스에서 같은 이름+주소는 한 번만
CREATE UNIQUE INDEX IF NOT EXISTS uq_places_source_name_addr
  ON places (source, name, COALESCE(address, ''));

CREATE INDEX IF NOT EXISTS idx_places_geom     ON places USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_places_category ON places (category);
CREATE INDEX IF NOT EXISTS idx_places_district ON places (district);
CREATE INDEX IF NOT EXISTS idx_places_rawdata  ON places USING GIN (raw_data);

-- ============================================================
-- events
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
  event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       VARCHAR(200) NOT NULL,
  category    VARCHAR(50),
  place_name  TEXT,
  address     TEXT,
  district    VARCHAR(50),
  geom        GEOMETRY(Point, 4326),
  date_start  DATE,
  date_end    DATE,
  price       TEXT,
  poster_url  TEXT,
  detail_url  TEXT,
  summary     TEXT,
  source      VARCHAR(50),
  raw_data    JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- 중복 방지: 같은 소스의 같은 제목+시작일
CREATE UNIQUE INDEX IF NOT EXISTS uq_events_source_title_date
  ON events (source, title, COALESCE(date_start, '1970-01-01'::date));

CREATE INDEX IF NOT EXISTS idx_events_geom     ON events USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_events_district ON events (district);
CREATE INDEX IF NOT EXISTS idx_events_date     ON events (date_start, date_end);

-- ============================================================
-- population_stats
-- ============================================================
CREATE TABLE IF NOT EXISTS population_stats (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  base_date       DATE NOT NULL,
  time_slot       SMALLINT NOT NULL,
  adm_dong_code   VARCHAR(20) NOT NULL,
  adm_dong_name   VARCHAR(50),
  district        VARCHAR(50),
  total_pop       INTEGER,
  raw_data        JSONB,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- 자연키: (날짜, 시간대, 행정동)
CREATE UNIQUE INDEX IF NOT EXISTS uq_popstats_date_slot_dong
  ON population_stats (base_date, time_slot, adm_dong_code);

CREATE INDEX IF NOT EXISTS idx_popstats_dong ON population_stats (adm_dong_code);
CREATE INDEX IF NOT EXISTS idx_popstats_date ON population_stats (base_date, time_slot);

-- ============================================================
-- administrative_districts
-- ============================================================
CREATE TABLE IF NOT EXISTS administrative_districts (
  adm_dong_code   VARCHAR(20) PRIMARY KEY,
  adm_dong_name   VARCHAR(50) NOT NULL,
  district        VARCHAR(50),
  geom            GEOMETRY(MultiPolygon, 4326)
);

CREATE INDEX IF NOT EXISTS idx_admdistrict_geom     ON administrative_districts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_admdistrict_district ON administrative_districts (district);

-- ============================================================
-- place_analysis (비정형 데이터 — 리뷰 LLM 분석 결과)
-- ============================================================
CREATE TABLE IF NOT EXISTS place_analysis (
    analysis_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id            UUID         NOT NULL REFERENCES places(place_id) ON DELETE CASCADE,
    google_place_id     VARCHAR(100),
    place_name          VARCHAR(200) NOT NULL,
    score_taste         NUMERIC(2,1),
    score_service       NUMERIC(2,1),
    score_atmosphere    NUMERIC(2,1),
    score_value         NUMERIC(2,1),
    score_cleanliness   NUMERIC(2,1),
    score_accessibility NUMERIC(2,1),
    keywords            TEXT[],
    summary             TEXT,
    review_count        INTEGER,
    source_breakdown    JSONB,
    analyzed_at         TIMESTAMPTZ  DEFAULT NOW(),
    ttl_expires_at      TIMESTAMPTZ  DEFAULT NOW() + INTERVAL '7 days',
    UNIQUE(place_id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_place ON place_analysis(place_id);
CREATE INDEX IF NOT EXISTS idx_analysis_expires ON place_analysis(ttl_expires_at);
