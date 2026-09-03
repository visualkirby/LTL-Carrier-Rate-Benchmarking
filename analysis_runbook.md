# LTL Rate Benchmarking - Analysis Runbook

Full sequence from raw data to the first benchmark and scored-quotes tables, in
BigQuery and Excel. Work through it top to bottom; skip a phase whose checks
already pass.

This runbook builds the plain lane-band benchmark and a working `scored_quotes`
flag. The final method refines that into a leave-one-out benchmark and a rate
index, and adds the carrier scorecards and the routing recommendation. That full
chain is the seven files in `queries/`; the methodology decisions behind it are
in the README.

Business question: when a small shipper gets an LTL quote, how does it know whether
that rate is competitive for the lane and freight class?

---

## Phase 0 - Data (done)

`generate_dataset.py` produces a small star schema:

| File | Rows | Notes |
|---|---|---|
| `fact_shipments.csv` | 1,024 | one row per quoted shipment, FKs + measures |
| `dim_lanes.csv` | 12 | lane_id, origin/dest, distance |
| `dim_carriers.csv` | 5 | carrier_name, scac |
| `dim_nmfc_classes.csv` | 15 | nmfc_class, density_band, example_commodity |
| `dim_weight_breaks.csv` | 5 | tier code, lb ranges, label |
| `ltl_shipment_quotes.csv` | 1,024 | denormalized (fact joined to dims), for Excel |

Generating parameters (carrier market factor, class multipliers, tier factors) are
deliberately NOT in any file. A real analyst discovers carrier pricing position from
the data.

---

## Phase 1 - BigQuery: dataset + 5 tables

### 1.1 Create the dataset

Console, project `ltl-benchmarking`: Create Dataset, ID `ltl_benchmarking`, location US.

### 1.2 Create each table

For each of the 5 tables: **Create Table** > Source = **Upload**, browse the matching
CSV, File format CSV > Schema: toggle **Edit as text**, paste the JSON below > expand
**Advanced options**, set **Header rows to skip** = **1** > Create table.

Using Edit-as-text avoids the trailing-space bug that hand-typed field boxes caused.

**fact_shipments**
```json
[
  {"name":"shipment_id","type":"STRING","mode":"REQUIRED"},
  {"name":"quote_date","type":"DATE","mode":"NULLABLE"},
  {"name":"lane_id","type":"STRING","mode":"REQUIRED"},
  {"name":"carrier_name","type":"STRING","mode":"REQUIRED"},
  {"name":"nmfc_class","type":"FLOAT","mode":"REQUIRED"},
  {"name":"weight_lbs","type":"INTEGER","mode":"NULLABLE"},
  {"name":"weight_break_tier","type":"STRING","mode":"NULLABLE"},
  {"name":"base_cwt_rate","type":"FLOAT","mode":"NULLABLE"},
  {"name":"accessorials","type":"STRING","mode":"NULLABLE"},
  {"name":"accessorial_total","type":"INTEGER","mode":"NULLABLE"},
  {"name":"fuel_surcharge","type":"FLOAT","mode":"NULLABLE"},
  {"name":"quoted_rate_total","type":"FLOAT","mode":"NULLABLE"}
]
```

**dim_lanes**
```json
[
  {"name":"lane_id","type":"STRING","mode":"REQUIRED"},
  {"name":"origin_city","type":"STRING","mode":"NULLABLE"},
  {"name":"origin_state","type":"STRING","mode":"NULLABLE"},
  {"name":"dest_city","type":"STRING","mode":"NULLABLE"},
  {"name":"dest_state","type":"STRING","mode":"NULLABLE"},
  {"name":"distance_miles","type":"INTEGER","mode":"NULLABLE"}
]
```

**dim_carriers**
```json
[
  {"name":"carrier_name","type":"STRING","mode":"REQUIRED"},
  {"name":"scac","type":"STRING","mode":"NULLABLE"}
]
```

**dim_nmfc_classes**
```json
[
  {"name":"nmfc_class","type":"FLOAT","mode":"REQUIRED"},
  {"name":"density_band","type":"STRING","mode":"NULLABLE"},
  {"name":"example_commodity","type":"STRING","mode":"NULLABLE"}
]
```

**dim_weight_breaks**
```json
[
  {"name":"weight_break_tier","type":"STRING","mode":"REQUIRED"},
  {"name":"min_weight_lbs","type":"INTEGER","mode":"NULLABLE"},
  {"name":"max_weight_lbs","type":"INTEGER","mode":"NULLABLE"},
  {"name":"tier_label","type":"STRING","mode":"NULLABLE"}
]
```

### 1.3 Verify

```sql
-- expect 1024
SELECT COUNT(*) AS rows FROM ltl_benchmarking.fact_shipments;

-- expect zero rows (no hidden whitespace in any column name)
SELECT table_name, column_name, LENGTH(column_name) AS len
FROM ltl_benchmarking.INFORMATION_SCHEMA.COLUMNS
WHERE LENGTH(column_name) != LENGTH(TRIM(column_name));

-- keys line up: expect 49 lane-carrier combinations, 1024 total quotes
SELECT COUNT(*) AS lane_carrier_combos, SUM(quotes) AS total_quotes
FROM (
  SELECT f.lane_id, f.carrier_name, COUNT(*) AS quotes
  FROM ltl_benchmarking.fact_shipments f
  JOIN ltl_benchmarking.dim_lanes l USING (lane_id)
  JOIN ltl_benchmarking.dim_carriers c USING (carrier_name)
  GROUP BY 1, 2
);
```

If the whitespace query returns a row, fix that column (recreate the table with the
JSON schema) before continuing, or every join downstream breaks.

---

## Phase 2 - Section 1: lane-level rate benchmarks (SQL)

The benchmark unit is `base_cwt_rate`, the linehaul cost per hundredweight. Fuel and
accessorials are already excluded from that column. Group by lane and a freight-class
band, because class moves the CWT rate too much to pool a whole lane together.

Class bands (4). Each band holds classes within ~1.15-1.3x of each other, so a
within-cell rate gap reads as overpayment, not just a denser load:

| band | classes |
|---|---|
| low | 50-70 |
| mid | 77.5-110 |
| high | 125-150 |
| vhigh | 175-250 |

```sql
-- 2.1 Banded view
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

-- 2.2 Lane-level benchmarks
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
GROUP BY lane_id, class_band
ORDER BY lane_id, class_band;
```

`APPROX_QUANTILES(col, 100)[OFFSET(50)]` is the BigQuery idiom for a median inside a
GROUP BY. With ~20-30 rows per cell it is exact for practical purposes.

### Check

```sql
SELECT class_band,
       COUNT(*) AS cells,
       ROUND(AVG(stddev_cwt_rate / benchmark_cwt_rate), 3) AS avg_cv,
       COUNTIF(low_confidence) AS thin_cells
FROM ltl_benchmarking.lane_benchmarks
GROUP BY class_band ORDER BY class_band;
```

`avg_cv` (coefficient of variation, spread relative to the benchmark) should sit near
0.20-0.25 for all four bands. If one band is much higher, its class range is still
too wide. A handful of `thin_cells` is fine, the `low_confidence` flag carries that.

---

## Phase 3 - Section 2: flag above-benchmark quotes (SQL)

Join every quote to its lane-band benchmark, score it as a ratio, flag the ones in
the top quarter for that cell. On the job this is freight cost variance analysis: the
"which shipments did we overpay on" report that feeds a carrier dispute or a re-bid.

- `rate_index = base_cwt_rate / benchmark_cwt_rate * 100`. 100 is at benchmark, 112 is
  12% above. A ratio compares across lanes and bands at different absolute rate levels.
- Working flag: `base_cwt_rate > p75_cwt_rate`. Section 4 sets the real threshold.

```sql
CREATE OR REPLACE TABLE ltl_benchmarking.scored_quotes AS
SELECT
  s.shipment_id, s.quote_date, s.lane_id, s.carrier_name, s.nmfc_class,
  s.class_band, s.weight_lbs, s.base_cwt_rate,
  b.benchmark_cwt_rate, b.p75_cwt_rate,
  ROUND(s.base_cwt_rate / b.benchmark_cwt_rate * 100, 1) AS rate_index,
  s.base_cwt_rate > b.p75_cwt_rate AS above_p75,
  b.low_confidence AS benchmark_low_confidence
FROM ltl_benchmarking.v_shipments_banded s
JOIN ltl_benchmarking.lane_benchmarks b USING (lane_id, class_band);
```

### Check

```sql
SELECT carrier_name,
       COUNT(*) AS quotes,
       ROUND(AVG(rate_index), 1) AS avg_rate_index,
       COUNTIF(above_p75) AS flagged,
       ROUND(COUNTIF(above_p75) / COUNT(*) * 100, 1) AS flagged_pct
FROM ltl_benchmarking.scored_quotes
GROUP BY carrier_name
ORDER BY avg_rate_index DESC;
```

Expect a spread in `avg_rate_index`, with BlueRidge LTL highest (it prices about 8%
over market) and Piedmont Freight Line lowest. That is the carrier position Section 3
formalizes into a scorecard.

---

## Phase 4 - Excel (Power Query + Power Pivot)

Workbook: `LTL_Rate_Benchmarking.xlsx` in the project folder.

### 4.1 Export the benchmark table

BigQuery: `SELECT * FROM ltl_benchmarking.lane_benchmarks ORDER BY lane_id, class_band`,
then **Save Results > CSV (local file)**, save as `lane_benchmarks.csv` in the project
folder (overwrite any old copy).

### 4.2 Load the quotes

Data > Get Data > From Text/CSV > `ltl_shipment_quotes.csv` > **Transform Data**.
In the editor, confirm column types, then:
Add Column > **Conditional Column**, name `class_band`:
- if `nmfc_class` is less than or equal to `70` then `"low"`
- else if `nmfc_class` is less than or equal to `110` then `"mid"`
- else if `nmfc_class` is less than or equal to `150` then `"high"`
- else `"vhigh"`

Home > Close & Load To > Only Create Connection, tick Add to Data Model.

### 4.3 Load the benchmark table

Data > Get Data > From Text/CSV > `lane_benchmarks.csv` > Transform Data > Close &
Load To > Only Create Connection, Add to Data Model.

### 4.4 Merge

Duplicate or reference the `ltl_shipment_quotes` query (right-click > Reference), name
it `scored_quotes`. Home > **Merge Queries**:
- top: `scored_quotes`, Ctrl-click `lane_id` then `class_band`
- bottom: `lane_benchmarks`, Ctrl-click `lane_id` then `class_band`
- Join Kind: Left Outer

Expand the merged column, keep `benchmark_cwt_rate` and `p75_cwt_rate` only.
Add Column > Custom Column:
- `rate_index` = `Number.Round([base_cwt_rate] / [benchmark_cwt_rate] * 100, 1)`
- `above_p75` = `[base_cwt_rate] > [p75_cwt_rate]`

Close & Load To > Only Create Connection, Add to Data Model.

### 4.5 Section 1 pivot (Excel computes the benchmark independently, as a cross-check)

Insert > PivotTable > From Data Model, against the `ltl_shipment_quotes` table.
Measures (Power Pivot):
- `Quote Count := COUNTROWS(ltl_shipment_quotes)`
- `Benchmark CWT := MEDIAN(ltl_shipment_quotes[base_cwt_rate])`
- `P25 CWT := PERCENTILE.INC(ltl_shipment_quotes[base_cwt_rate], 0.25)`
- `P75 CWT := PERCENTILE.INC(ltl_shipment_quotes[base_cwt_rate], 0.75)`
- `Rate StdDev := STDEV.P(ltl_shipment_quotes[base_cwt_rate])`
- `Low Confidence := IF([Quote Count] < 10, "thin", "")`

Rows: `lane_id` then `class_band`. Values: the six measures. This should match
`lane_benchmarks` from SQL within rounding, which is the validation.

### 4.6 Scored-quotes view

Insert > PivotTable from Data Model against `scored_quotes`:
Rows `carrier_name`, Values `Average of rate_index` and `Count of above_p75` (filter
to TRUE), or build a carrier summary table. Should match the Phase 3 carrier check.

---

## Where this leaves you

- SQL: `v_shipments_banded`, `lane_benchmarks`, `scored_quotes` tables built
- Excel: quotes + benchmarks loaded, merged, scored, two pivots

From here the analysis moves to `queries/03` through `queries/07`: the leave-one-out
benchmark, the rate index, the carrier and carrier-lane scorecards, and the
`lane_carrier_recommendation` routing table. The findings memo reads off that last
table.
