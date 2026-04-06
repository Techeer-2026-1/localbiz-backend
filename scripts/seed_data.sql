-- PoC 테스트용 Seed 데이터 — 서울 강남/서초/마포 지역 샘플 장소
-- 실행: psql -h localhost -U localbiz -d localbiz -f scripts/seed_data.sql

INSERT INTO places (name, category, sub_category, address, district, geom, phone, google_place_id, image_url, booking_url, raw_data, source)
VALUES

-- ===== 강남구 음식점 =====
(
    '봉피양 강남점',
    'restaurant', '한식/냉면',
    '서울특별시 강남구 테헤란로 133',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0338, 37.5003), 4326),
    '02-556-5890',
    'ChIJN1t_tDeuEmsRUsoyG83frY4',  -- 샘플 google_place_id
    NULL,
    'https://booking.naver.com/booking/6/bizes/145027',
    '{"업태":"냉면/한식","주차":"가능","영업시간":"11:00~22:00","메뉴":["평양냉면","비빔냉면","왕만두"]}'::jsonb,
    'seed'
),
(
    '스시코우지',
    'restaurant', '일식/스시',
    '서울특별시 강남구 도산대로 318',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0284, 37.5229), 4326),
    '02-541-6200',
    NULL,
    NULL,
    NULL,
    '{"업태":"일식","주차":"불가","영업시간":"12:00~22:00","특징":"오마카세 전문"}'::jsonb,
    'seed'
),
(
    '이탈리아노 강남',
    'restaurant', '양식/이탈리안',
    '서울특별시 강남구 역삼동 825-10',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0330, 37.4985), 4326),
    '02-567-1234',
    NULL,
    NULL,
    NULL,
    '{"업태":"이탈리안","주차":"가능","영업시간":"11:30~22:30","메뉴":["파스타","피자","리조또"]}'::jsonb,
    'seed'
),

-- ===== 강남구 카페 =====
(
    '블루보틀 삼청동점',
    'cafe', '스페셜티 커피',
    '서울특별시 강남구 삼성로 212',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0583, 37.5122), 4326),
    NULL,
    NULL,
    NULL,
    NULL,
    '{"업태":"카페","주차":"불가","영업시간":"08:00~21:00","특징":"스페셜티 원두"}'::jsonb,
    'seed'
),
(
    '카페 드 파리 강남',
    'cafe', '디저트 카페',
    '서울특별시 강남구 압구정로 46길 50',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0302, 37.5269), 4326),
    '02-544-3366',
    NULL,
    NULL,
    NULL,
    '{"업태":"카페/베이커리","주차":"불가","영업시간":"09:00~22:00","특징":"프렌치 디저트"}'::jsonb,
    'seed'
),

-- ===== 강남구 헬스장 =====
(
    '짐박스 강남',
    'gym', '크로스핏',
    '서울특별시 강남구 역삼동 737-20',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0322, 37.4990), 4326),
    '02-555-9988',
    NULL,
    NULL,
    'https://booking.naver.com/booking/6/bizes/300001',
    '{"업태":"헬스/크로스핏","주차":"불가","영업시간":"06:00~23:00","특징":"24시간 운영"}'::jsonb,
    'seed'
),

-- ===== 서초구 음식점 =====
(
    '교촌치킨 서초점',
    'restaurant', '치킨',
    '서울특별시 서초구 반포대로 58',
    'seocho',
    ST_SetSRID(ST_MakePoint(127.0083, 37.5035), 4326),
    '02-533-0133',
    NULL,
    NULL,
    'https://www.kyochon.com',
    '{"업태":"치킨","주차":"가능","영업시간":"11:00~24:00","배달":"가능"}'::jsonb,
    'seed'
),

-- ===== 마포구 카페 =====
(
    '연남동 경의선숲길카페',
    'cafe', '분위기 카페',
    '서울특별시 마포구 연남동 240-59',
    'mapo',
    ST_SetSRID(ST_MakePoint(126.9240, 37.5630), 4326),
    NULL,
    NULL,
    NULL,
    NULL,
    '{"업태":"카페","주차":"불가","영업시간":"10:00~23:00","특징":"경의선숲길 뷰"}'::jsonb,
    'seed'
),
(
    '망원동 브런치카페',
    'cafe', '브런치',
    '서울특별시 마포구 망원동 473-7',
    'mapo',
    ST_SetSRID(ST_MakePoint(126.9027, 37.5561), 4326),
    '02-333-7788',
    NULL,
    NULL,
    NULL,
    '{"업태":"카페/브런치","주차":"불가","영업시간":"09:00~21:00","특징":"홈메이드 베이크"}'::jsonb,
    'seed'
),

-- ===== 공원 =====
(
    '선정릉',
    'park', '역사공원',
    '서울특별시 강남구 선릉로 100길 1',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0474, 37.5094), 4326),
    '02-568-1393',
    'ChIJxWLy_aihfDURn-BVT08DNAU',
    NULL,
    NULL,
    '{"관리기관":"문화재청","입장료":"성인 1000원","개방시간":"06:00~21:00","특징":"조선왕릉, 산책로"}'::jsonb,
    'seed'
),

-- ===== 미용실 =====
(
    '준오헤어 강남점',
    'beauty', '미용실',
    '서울특별시 강남구 강남대로 382',
    'gangnam',
    ST_SetSRID(ST_MakePoint(127.0276, 37.4979), 4326),
    '02-544-6604',
    NULL,
    NULL,
    'https://booking.naver.com/booking/6/bizes/2001',
    '{"업태":"미용실","주차":"불가","영업시간":"10:00~20:00","특징":"커트/펌/염색 전문"}'::jsonb,
    'seed'
)

ON CONFLICT DO NOTHING;
