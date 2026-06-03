-- MySQL 版（生产可选）。assistantService 默认使用 SQLite，见 src/spider/antexiadan/seckill_store.py init_db()
-- 源文件同步：webAuto/docs/安特/antexiadan-seckill-db-schema.sql

-- 安特 PC 商城 · 限时秒杀商品库表结构
-- 站点：https://pc.antexiadan.com
-- 数据源：GET https://pcapi.antexiadan.com/v1/home/seckill-list

CREATE TABLE IF NOT EXISTS antexiadan_seckill_fetch_batch (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '批次 ID',
  fetched_at      DATETIME        NOT NULL COMMENT '本端抓取完成时间',
  server_time     DATETIME        NULL     COMMENT '接口返回 server_time',
  server_unix     INT UNSIGNED    NULL,
  api_version     VARCHAR(16)     NULL,
  source          VARCHAR(32)     NOT NULL DEFAULT 'pcapi',
  item_count      INT UNSIGNED    NOT NULL DEFAULT 0,
  api_flag        INT             NULL,
  api_msg         VARCHAR(255)    NULL,
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_fetched_at (fetched_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS antexiadan_seckill_product (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  seckill_id          VARCHAR(32)     NOT NULL,
  goods_id            VARCHAR(32)     NOT NULL,
  goods_basic_id      VARCHAR(32)     NULL,
  title               VARCHAR(512)    NOT NULL,
  price_min           DECIMAL(12,2)   NULL,
  price_max           DECIMAL(12,2)   NULL,
  price_display       VARCHAR(64)     NULL,
  group_title         VARCHAR(32)     NULL,
  slot_time           VARCHAR(32)     NULL,
  group_sub_title     VARCHAR(32)     NULL,
  activity_status     VARCHAR(32)     NOT NULL,
  start_time          DATETIME        NOT NULL,
  end_time            DATETIME        NOT NULL,
  start_unix          INT UNSIGNED    NOT NULL,
  end_unix            INT UNSIGNED    NOT NULL,
  seckill_state       CHAR(1)         NULL,
  seckill_image       VARCHAR(512)    NULL,
  goods_url           VARCHAR(512)    NULL,
  goods_is_offline    TINYINT(1)      NOT NULL DEFAULT 0,
  homepage_display    TINYINT(1)      NOT NULL DEFAULT 1,
  is_flash_title      TINYINT(1)      NOT NULL DEFAULT 1,
  last_fetch_batch_id BIGINT UNSIGNED NULL,
  last_fetched_at     DATETIME        NOT NULL,
  created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_seckill_id (seckill_id),
  KEY idx_start_time (start_time),
  KEY idx_activity_status (activity_status),
  KEY idx_group_slot (group_title, slot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS antexiadan_seckill_product_snapshot (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  fetch_batch_id      BIGINT UNSIGNED NOT NULL,
  seckill_id          VARCHAR(32)     NOT NULL,
  goods_id            VARCHAR(32)     NOT NULL,
  goods_basic_id      VARCHAR(32)     NULL,
  title               VARCHAR(512)    NOT NULL,
  price_min           DECIMAL(12,2)   NULL,
  price_max           DECIMAL(12,2)   NULL,
  price_display       VARCHAR(64)     NULL,
  group_title         VARCHAR(32)     NULL,
  slot_time           VARCHAR(32)     NULL,
  group_sub_title     VARCHAR(32)     NULL,
  activity_status     VARCHAR(32)     NOT NULL,
  start_time          DATETIME        NOT NULL,
  end_time            DATETIME        NOT NULL,
  start_unix          INT UNSIGNED    NOT NULL,
  end_unix            INT UNSIGNED    NOT NULL,
  seckill_state       CHAR(1)         NULL,
  seckill_image       VARCHAR(512)    NULL,
  goods_url           VARCHAR(512)    NULL,
  goods_is_offline    TINYINT(1)      NOT NULL DEFAULT 0,
  homepage_display    TINYINT(1)      NOT NULL DEFAULT 1,
  created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_batch_seckill (fetch_batch_id, seckill_id),
  KEY idx_fetch_batch (fetch_batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
