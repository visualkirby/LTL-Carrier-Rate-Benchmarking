-- 05_carrier_lane_scorecard.sql
-- carrier_lane_scorecard: one row per carrier-lane. Median and p75 rate index
-- show price position; excess_linehaul_usd is the dollar impact, summed as
-- (quoted rate - benchmark) per hundredweight times the shipment weight.
-- Negative means the carrier came in under market on that lane.

CREATE OR REPLACE TABLE ltl_benchmarking.carrier_lane_scorecard AS
SELECT
  carrier_name,
  lane_id,
  COUNT(*) AS quotes,
  ROUND(APPROX_QUANTILES(rate_index_loo, 100)[OFFSET(50)], 1) AS median_rate_index,
  ROUND(APPROX_QUANTILES(rate_index_loo, 100)[OFFSET(75)], 1) AS p75_rate_index,
  ROUND(SUM((base_cwt_rate - benchmark_loo) * weight_lbs / 100), 0) AS excess_linehaul_usd
FROM ltl_benchmarking.scored_quotes_loo
GROUP BY 1, 2;
