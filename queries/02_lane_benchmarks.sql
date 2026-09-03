-- 02_lane_benchmarks.sql
-- lane_benchmarks: the plain lane x class-band benchmark, median linehaul rate
-- per cell plus the interquartile range and spread. This is the descriptive
-- view; the leave-one-out version in 03 is what carriers are actually scored
-- against.
-- APPROX_QUANTILES(col, 100)[OFFSET(50)] is the BigQuery idiom for a median
-- inside a GROUP BY. With ~20-30 rows per cell it is exact for practical use.

CREATE OR REPLACE TABLE ltl_benchmarking.lane_benchmarks AS
SELECT
  lane_id,
  class_band,
  COUNT(*) AS n_quotes,
  ROUND(APPROX_QUANTILES(base_cwt_rate, 100)[OFFSET(50)], 2) AS benchmark_cwt_rate,
  ROUND(APPROX_QUANTILES(base_cwt_rate, 100)[OFFSET(25)], 2) AS p25_cwt_rate,
  ROUND(APPROX_QUANTILES(base_cwt_rate, 100)[OFFSET(75)], 2) AS p75_cwt_rate,
  ROUND(STDDEV(base_cwt_rate), 2) AS stddev_cwt_rate,
  COUNT(*) < 10 AS low_confidence
FROM ltl_benchmarking.v_shipments_banded
GROUP BY lane_id, class_band;
