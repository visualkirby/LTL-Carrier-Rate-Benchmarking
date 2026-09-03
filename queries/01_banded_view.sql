-- 01_banded_view.sql
-- v_shipments_banded: adds the freight-class band used to group every benchmark.
-- Four bands. Each holds classes within ~1.15-1.3x of each other in rate, so a
-- within-cell rate gap reads as overpayment rather than a denser load. A first
-- attempt at three bands lumped classes spanning ~1.6x into one cell and gave a
-- 37% within-cell coefficient of variation.

CREATE OR REPLACE VIEW ltl_benchmarking.v_shipments_banded AS
SELECT
  f.*,
  CASE
    WHEN f.nmfc_class <= 70  THEN 'low'
    WHEN f.nmfc_class <= 110 THEN 'mid'
    WHEN f.nmfc_class <= 150 THEN 'high'
    ELSE 'vhigh'
  END AS class_band
FROM ltl_benchmarking.fact_shipments f;
