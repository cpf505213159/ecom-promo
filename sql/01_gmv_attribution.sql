-- 大促 GMV 三层分解 + 品类结构（mix / within）
-- 方言：MySQL 8.0；两期用 year 参数区分（2024 基线 / 2025 本期）
--
-- 关键是先统一口径，再谈分解：
--   uv      去重 UV（跨端已合并）
--   orders  支付订单数，剔除退款与测试单
--   gmv     支付金额，剔除运费与退款
--   cvr     orders / uv
--   aov     gmv / orders
-- 三个指标必须来自同一批订单，否则分解会出现「解释不了的残差」。

WITH base AS (
    SELECT
        category_id,
        SUM(uv)                                           AS uv,
        SUM(orders)                                       AS orders,
        SUM(gmv)                                          AS gmv,
        COUNT(DISTINCT stat_date)                         AS days
    FROM dws_promo_category_daily
    WHERE promo_id = '2024_double11'
    GROUP BY category_id
),

cur AS (
    SELECT
        category_id,
        SUM(uv)                                           AS uv,
        SUM(orders)                                       AS orders,
        SUM(gmv)                                          AS gmv,
        COUNT(DISTINCT stat_date)                         AS days
    FROM dws_promo_category_daily
    WHERE promo_id = '2025_double11'
    GROUP BY category_id
),

tot AS (
    SELECT
        (SELECT SUM(uv) FROM base)                        AS uv0,
        (SELECT SUM(orders) FROM base)                    AS ord0,
        (SELECT SUM(gmv) FROM base)                       AS gmv0,
        (SELECT SUM(uv) FROM cur)                         AS uv1,
        (SELECT SUM(orders) FROM cur)                     AS ord1,
        (SELECT SUM(gmv) FROM cur)                        AS gmv1,
        (SELECT MAX(days) FROM base)                      AS days0,
        (SELECT MAX(days) FROM cur)                       AS days1
)

-- ① 三层链式分解：三项之和应精确等于增量（闭合误差应为 0）
SELECT
    gmv1 - gmv0                                           AS gmv_delta,
    (uv1 - uv0) * (ord0 / NULLIF(uv0, 0)) * (gmv0 / NULLIF(ord0, 0)) * days0
                                                          AS uv_effect,
    uv1 * ((ord1 / NULLIF(uv1, 0)) - (ord0 / NULLIF(uv0, 0))) * (gmv0 / NULLIF(ord0, 0)) * days1
                                                          AS cvr_effect,
    uv1 * (ord1 / NULLIF(uv1, 0)) * ((gmv1 / NULLIF(ord1, 0)) - (gmv0 / NULLIF(ord0, 0))) * days1
                                                          AS aov_effect,
    (gmv1 - gmv0) - (
        (uv1 - uv0) * (ord0 / NULLIF(uv0, 0)) * (gmv0 / NULLIF(ord0, 0)) * days0
      + uv1 * ((ord1 / NULLIF(uv1, 0)) - (ord0 / NULLIF(uv0, 0))) * (gmv0 / NULLIF(ord0, 0)) * days1
      + uv1 * (ord1 / NULLIF(uv1, 0)) * ((gmv1 / NULLIF(ord1, 0)) - (gmv0 / NULLIF(ord0, 0))) * days1
    )                                                     AS closure_error
FROM tot;

-- ② 结构效应 vs 自身效应：CVR 按 UV 份额加权，AOV 按订单份额加权
WITH w AS (
    SELECT
        b.category_id,
        b.orders / NULLIF((SELECT SUM(orders) FROM base), 0) AS ord_share0,
        c.orders / NULLIF((SELECT SUM(orders) FROM cur), 0)  AS ord_share1,
        b.uv / NULLIF((SELECT SUM(uv) FROM base), 0)         AS uv_share0,
        c.uv / NULLIF((SELECT SUM(uv) FROM cur), 0)          AS uv_share1,
        b.orders / NULLIF(b.uv, 0)                           AS cvr0,
        c.orders / NULLIF(c.uv, 0)                           AS cvr1,
        b.gmv / NULLIF(b.orders, 0)                          AS aov0,
        c.gmv / NULLIF(c.orders, 0)                          AS aov1
    FROM base b JOIN cur c ON c.category_id = b.category_id
)
SELECT
    SUM((uv_share1 - uv_share0) * cvr0)                      AS cvr_mix,
    SUM(uv_share1 * (cvr1 - cvr0))                           AS cvr_within,
    SUM((ord_share1 - ord_share0) * aov0)                    AS aov_mix,
    SUM(ord_share1 * (aov1 - aov0))                          AS aov_within
FROM w;

-- ③ 品类贡献：谁在贡献增量，谁的份额在变
SELECT
    b.category_id,
    b.gmv AS gmv0,
    c.gmv AS gmv1,
    (c.gmv - b.gmv) / NULLIF((SELECT SUM(gmv) FROM cur) - (SELECT SUM(gmv) FROM base), 0) AS contrib,
    (c.uv / NULLIF((SELECT SUM(uv) FROM cur), 0)
     - b.uv / NULLIF((SELECT SUM(uv) FROM base), 0)) * 100  AS uv_share_chg_pp
FROM base b JOIN cur c ON c.category_id = b.category_id
ORDER BY contrib DESC;
