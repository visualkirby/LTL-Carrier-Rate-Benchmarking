-- 06_carrier_scorecard.sql
-- carrier_scorecard: one row per carrier across every lane it serves.
-- median_rate_index is the overall price position, rate_index_iqr is how
-- consistent the quotes are (a wide IQR means the carrier is unpredictable
-- lane to lane), pct_over_110 is the share of quotes that land more than 10%
-- above market.

CREATE OR REPLACE TABLE ltl_benchmarking.carrier_scorecard AS
SELECT
  carrier_name,
  COUNT(DISTINCT lane_id) AS lanes_served,
  COUNT(*) AS quotes,
  ROUND(APPROX_QUANTILES(rate_index_loo, 100)[OFFSET(50)], 1) AS median_rate_index,
  ROUND(APPROX_QUANTILES(rate_index_loo, 100)[OFFSET(75)], 1)
    - ROUND(APPROX_QUANTILES(rate_index_loo, 100)[OFFSET(25)], 1) AS rate_index_iqr,
  ROUND(COUNTIF(rate_index_loo > 110) / COUNT(*) * 100, 1) AS pct_over_110
FROM ltl_benchmarking.scored_quotes_loo
GROUP BY 1
ORDER BY median_rate_index;
