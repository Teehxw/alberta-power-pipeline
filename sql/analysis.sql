-- analysis.sql: example questions to ask the pool_price table.
-- Run with:  sqlite3 data/alberta_power.db < sql/analysis.sql
-- (SQLite 3.25+ is needed for window functions.)
-- timestamp_mpt is Alberta local time stored as text 'YYYY-MM-DD HH:MM:SS'.

.headers on
.mode column

-- 1. Average price by hour of day (Alberta time).
--    When during the day is electricity most expensive?
SELECT
    CAST(strftime('%H', timestamp_mpt) AS INTEGER) AS hour_of_day,
    ROUND(AVG(pool_price), 2)                      AS avg_price,
    COUNT(*)                                       AS hours_counted
FROM pool_price
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- 2. Price spikes by month (CTE).
--    How many hours per month were at or above $500/MWh (the same threshold as checks.py)?
WITH monthly AS (
    SELECT
        strftime('%Y-%m', timestamp_mpt)                    AS month,
        SUM(CASE WHEN pool_price >= 500 THEN 1 ELSE 0 END)  AS spike_hours,
        COUNT(*)                                            AS total_hours,
        MAX(pool_price)                                     AS max_price
    FROM pool_price
    GROUP BY month
)
SELECT
    month,
    spike_hours,
    total_hours,
    ROUND(100.0 * spike_hours / total_hours, 2) AS pct_spike_hours,
    max_price
FROM monthly
ORDER BY month;

-- 3. The 3 most expensive hours in each month (window function: RANK).
WITH ranked AS (
    SELECT
        strftime('%Y-%m', timestamp_mpt) AS month,
        timestamp_mpt,
        pool_price,
        RANK() OVER (
            PARTITION BY strftime('%Y-%m', timestamp_mpt)
            ORDER BY pool_price DESC
        ) AS price_rank
    FROM pool_price
)
SELECT month, price_rank, timestamp_mpt, pool_price
FROM ranked
WHERE price_rank <= 3
ORDER BY month, price_rank;

-- 4. Daily average price, change from the day before (LAG) and a 7-day moving average.
WITH daily AS (
    SELECT
        date(timestamp_mpt)       AS day,
        ROUND(AVG(pool_price), 2) AS avg_price
    FROM pool_price
    GROUP BY day
)
SELECT
    day,
    avg_price,
    ROUND(avg_price - LAG(avg_price) OVER (ORDER BY day), 2) AS change_vs_prev_day,
    ROUND(AVG(avg_price) OVER (
        ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2)                                                    AS moving_avg_7d
FROM daily
ORDER BY day;
