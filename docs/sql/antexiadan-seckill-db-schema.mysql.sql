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

-- 安特 PC 商城 · 商品搜索缓存（search-goods-list）
-- 数据源：POST https://pcapi.antexiadan.com/v1/selection/search-goods-list
-- 用途：按 keyword（货号/搜索词）缓存安特商品信息，供秒杀预购对照等场景复用

CREATE TABLE IF NOT EXISTS antexiadan_goods_search (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  keyword         VARCHAR(64)     NOT NULL COMMENT '搜索关键词，如 120002 / 008312',
  goods_id        VARCHAR(32)     NOT NULL COMMENT '安特 goods_id',
  goods_basic_id  VARCHAR(32)     NULL     COMMENT '安特 goods_basicid',
  goods_name      VARCHAR(512)    NOT NULL COMMENT '商品名称',
  goods_image     VARCHAR(512)    NULL     COMMENT '主图 URL',
  seckill_id      VARCHAR(32)     NULL     COMMENT '搜索 API 返回的 seckill_id，可能为 null',
  activity_type   INT             NULL     DEFAULT 0 COMMENT '活动类型，0=普通商品',
  activity_id     INT             NULL     DEFAULT 0 COMMENT '活动 ID',
  goods_url       VARCHAR(512)    NULL     COMMENT 'H5 商品链接',
  price_min       DECIMAL(12,2)   NULL     COMMENT '批发最低价',
  price_max       DECIMAL(12,2)   NULL     COMMENT '批发最高价',
  api_flag        INT             NULL     COMMENT '接口 flag',
  api_msg         VARCHAR(255)    NULL     COMMENT '接口 msg',
  searched_at     DATETIME        NOT NULL COMMENT '最近一次搜索时间',
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_keyword (keyword),
  KEY idx_goods_id (goods_id),
  KEY idx_seckill_id (seckill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
