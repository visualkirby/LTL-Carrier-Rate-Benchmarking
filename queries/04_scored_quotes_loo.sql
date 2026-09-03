-- 04_scored_quotes_loo.sql
-- scored_quotes_loo: every quote joined to its leave-one-out benchmark and
-- indexed against it. rate_index_loo = base_cwt_rate / benchmark_loo * 100, so
-- 100 is at benchmark and 112 is 12% above. A ratio compares across lanes and
-- bands that sit at different absolute rate levels.

CREATE OR REPLACE TABLE ltl_benchmarking.scored_quotes_loo AS
SELECT
  s.shipment_id,
  s.quote_date,
  s.lane_id,
  s.carrier_name,
  s.nmfc_class,
  s.class_band,
  s.weight_lbs,
  s.base_cwt_rate,
  l.benchmark_loo,
  l.other_quotes,
  ROUND(s.base_cwt_rate / l.benchmark_loo * 100, 1) AS rate_index_loo
FROM ltl_benchmarking.v_shipments_banded s
JOIN ltl_benchmarking.loo_benchmarks l USING (lane_id, class_band, carrier_name);
