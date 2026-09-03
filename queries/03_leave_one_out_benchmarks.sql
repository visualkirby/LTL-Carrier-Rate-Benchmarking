-- 03_leave_one_out_benchmarks.sql
-- loo_benchmarks: for each carrier in a lane-band cell, the median linehaul rate
-- of the OTHER carriers in that cell. A carrier that dominates a lane would
-- otherwise set the benchmark it is then measured against. Cells with no peer
-- carrier drop here (7 of 1,024 quotes).

CREATE OR REPLACE TABLE ltl_benchmarking.loo_benchmarks AS
WITH cell_carriers AS (
  SELECT DISTINCT lane_id, class_band, carrier_name
  FROM ltl_benchmarking.v_shipments_banded
)
SELECT
  cc.lane_id,
  cc.class_band,
  cc.carrier_name,
  COUNT(*) AS other_quotes,
  ROUND(APPROX_QUANTILES(s.base_cwt_rate, 100)[OFFSET(50)], 2) AS benchmark_loo
FROM cell_carriers cc
JOIN ltl_benchmarking.v_shipments_banded s
  ON s.lane_id = cc.lane_id
  AND s.class_band = cc.class_band
  AND s.carrier_name != cc.carrier_name
GROUP BY 1, 2, 3;
