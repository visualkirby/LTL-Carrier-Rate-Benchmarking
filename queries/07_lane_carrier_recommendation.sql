-- 07_lane_carrier_recommendation.sql
-- lane_carrier_recommendation: ranks the carriers on each lane by median rate
-- index and labels the cheapest 'primary' and the runner-up 'backup'. Only
-- carrier-lanes with at least 8 quotes are ranked; thinner ones are carried
-- through with thin_data = TRUE and no rank, since a median on 5 or 6 quotes
-- is not a reliable routing call.

CREATE OR REPLACE TABLE ltl_benchmarking.lane_carrier_recommendation AS
WITH qualified AS (
  SELECT
    lane_id,
    carrier_name,
    ROW_NUMBER() OVER (PARTITION BY lane_id ORDER BY median_rate_index) AS price_rank
  FROM ltl_benchmarking.carrier_lane_scorecard
  WHERE quotes >= 8
)
SELECT
  s.lane_id,
  s.carrier_name,
  s.quotes,
  s.median_rate_index,
  s.p75_rate_index,
  s.excess_linehaul_usd,
  q.price_rank,
  CASE q.price_rank WHEN 1 THEN 'primary' WHEN 2 THEN 'backup' ELSE NULL END AS recommendation,
  s.quotes < 8 AS thin_data
FROM ltl_benchmarking.carrier_lane_scorecard s
LEFT JOIN qualified q USING (lane_id, carrier_name);
