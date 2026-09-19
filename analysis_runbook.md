# LTL Rate Benchmarking - Analysis Runbook

Full sequence from raw data to the first benchmark and scored-quotes tables, in
BigQuery and Excel. Work through it top to bottom; skip a phase whose checks
already pass.

This runbook walks the full seven-query chain: the plain lane-band benchmark and
a working `scored_quotes` flag first, then the leave-one-out refinement, the rate
index, the carrier scorecards, and the routing recommendation. The methodology
decisions behind each step are in the README.

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

## Phase 5 - Section 3: leave-one-out benchmark (SQL)

A plain median lets a carrier that dominates a lane set the benchmark it is then
measured against. The leave-one-out (LOO) benchmark scores each carrier against the
median of the *other* carriers in that lane-band cell instead.

```sql
-- 5.1 Leave-one-out benchmark per carrier
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

-- 5.2 Score every quote against its LOO benchmark
CREATE OR REPLACE TABLE ltl_benchmarking.scored_quotes_loo AS
SELECT
  s.shipment_id, s.quote_date, s.lane_id, s.carrier_name, s.nmfc_class,
  s.class_band, s.weight_lbs, s.base_cwt_rate,
  l.benchmark_loo, l.other_quotes,
  ROUND(s.base_cwt_rate / l.benchmark_loo * 100, 1) AS rate_index_loo
FROM ltl_benchmarking.v_shipments_banded s
JOIN ltl_benchmarking.loo_benchmarks l USING (lane_id, class_band, carrier_name);
```

### Check

```sql
SELECT COUNT(*) AS scored_quotes FROM ltl_benchmarking.scored_quotes_loo;

-- rows dropped for having no peer carrier in their lane-band cell
SELECT COUNT(*) AS dropped
FROM ltl_benchmarking.v_shipments_banded s
LEFT JOIN ltl_benchmarking.scored_quotes_loo l USING (shipment_id)
WHERE l.shipment_id IS NULL;
```

7 of 1,024 quotes drop for having no peer carrier in their cell. `rate_index_loo`
runs a little wider than the plain `rate_index` from Phase 3, since a carrier is no
longer partly benchmarked against itself.

---

## Phase 6 - Section 4: carrier scorecards and routing recommendation (SQL)

Roll the LOO-scored quotes up two ways: by carrier-lane (where a specific carrier
stands on a specific lane, and what that cost in dollars) and by carrier overall
(where it stands across every lane it serves). Rank each lane's carriers by price
and label the cheapest the routing recommendation.

```sql
-- 6.1 Carrier-lane scorecard
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

-- 6.2 Carrier scorecard, across every lane served
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

-- 6.3 Routing recommendation
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
  s.lane_id, s.carrier_name, s.quotes, s.median_rate_index, s.p75_rate_index,
  s.excess_linehaul_usd, q.price_rank,
  CASE q.price_rank WHEN 1 THEN 'primary' WHEN 2 THEN 'backup' ELSE NULL END AS recommendation,
  s.quotes < 8 AS thin_data
FROM ltl_benchmarking.carrier_lane_scorecard s
LEFT JOIN qualified q USING (lane_id, carrier_name);
```

`excess_linehaul_usd` is the dollar-weighted overpayment: (quoted rate minus its LOO
benchmark) per hundredweight, times the shipment weight, summed. Negative means the
carrier came in under market on that carrier-lane. Only carrier-lanes with at least
8 quotes get ranked; a median on 5 or 6 quotes is not a reliable routing call, so
thinner ones carry through as `thin_data` with no rank.

### Check

```sql
SELECT * FROM ltl_benchmarking.carrier_scorecard ORDER BY median_rate_index;

-- carrier-lanes flagged more than one SD above market
SELECT COUNT(*) AS flagged_pairs, SUM(excess_linehaul_usd) AS total_excess_usd
FROM ltl_benchmarking.carrier_lane_scorecard
WHERE median_rate_index > 110;
```

The carrier scorecard should reproduce the Findings Memo's price-position table:
BlueRidge LTL and Crossroads Freight Co above 100, Piedmont Freight Line and
Palmetto Freight Systems around 8% under. The flagged-pairs total should land in
the same range as the memo's headline number, a bit over $7,700 in excess linehaul.
Exactly which carrier-lanes clear the 110 line is a judgment call on thin,
low-volume pairs, not a fixed target.

---

## Phase 7 - Excel: scorecards, routing, and dashboard

Export the four Phase 5-6 result tables the same way as Phase 4.1: BigQuery
**Save Results > CSV (local file)**, one per table, into the project folder.

- `scored_quotes_loo.csv`
- `carrier_lane_scorecard.csv`
- `carrier_scorecard.csv`
- `lane_carrier_recommendation.csv`

### 7.1 Load the scorecard and routing tables as sheets

`carrier_scorecard.csv` and `lane_carrier_recommendation.csv` land as visible
tables, not connection-only, since they *are* the Carrier Scorecard and Routing
sheets:

Data > Get Data > From Text/CSV > `carrier_scorecard.csv` > Transform Data >
confirm column types > Home > **Close & Load To > Table**, into a new sheet named
`Carrier Scorecard`.

Repeat for `lane_carrier_recommendation.csv` > **Close & Load To > Table**, into a
new sheet named `Routing`.

Conditional formatting on `Carrier Scorecard`: 2-color scale on `median_rate_index`,
green under 100 and red over 100, so a carrier's price position reads at a glance.
On `Routing`: highlight the `recommendation` column (`primary` / `backup`) and gray
out rows where `thin_data` is true.

### 7.2 Load the row-level and carrier-lane tables to the Data Model only

`scored_quotes_loo.csv` and `carrier_lane_scorecard.csv` feed the Dashboard's
slicers and measures. They don't need their own sheet:

Data > Get Data > From Text/CSV > `scored_quotes_loo.csv` > Transform Data > Close &
Load To > **Only Create Connection, Add to Data Model**. Repeat for
`carrier_lane_scorecard.csv`.

### 7.3 Dashboard: slicers and KPI strip

Insert > PivotTable > From Data Model, against `scored_quotes_loo`. Insert > Slicer
for `lane_id` and `carrier_name`, connect both to every pivot on the sheet (Slicer
**Report Connections**) so one selection drives the whole dashboard.

Power Pivot measures, defined against `scored_quotes_loo`:
- `Avg Rate Index := AVERAGE(scored_quotes_loo[rate_index_loo])`
- `Quote Count := COUNTROWS(scored_quotes_loo)`
- `Pct Over 110 := DIVIDE(CALCULATE(COUNTROWS(scored_quotes_loo), scored_quotes_loo[rate_index_loo] > 110), COUNTROWS(scored_quotes_loo))`

Lay the three out as a KPI strip (card visuals or a small table) at the top of the
sheet.

### 7.4 Dashboard: charts

- Carrier price-position chart: bar chart of `median_rate_index` by `carrier_name`,
  from a PivotChart against `carrier_lane_scorecard` or the `Avg Rate Index` measure
  sliced by carrier.
- Rate-vs-benchmark chart: `Avg Rate Index` by `class_band`, so a viewer can see
  which freight-class band carries the most above-market risk.

Both charts respond to the same two slicers as the KPI strip.

### Check

The `Carrier Scorecard` sheet's `median_rate_index` and `pct_over_110` columns
should match `carrier_scorecard` from the Phase 6 check query exactly. Slice the
Dashboard down to one carrier and confirm its `Pct Over 110` measure matches that
carrier's row on the Carrier Scorecard sheet.

---

## Where this leaves you

- SQL: the full seven-query chain, `v_shipments_banded` through
  `lane_carrier_recommendation`
- Excel: quotes and benchmarks merged and scored (Phase 4), the carrier scorecard
  and routing tables loaded as sheets, a Dashboard with two slicers, three DAX
  measures, and two charts (Phase 7)

`Findings_Memo.md` is the deliverable that reads off `lane_carrier_recommendation`
and `carrier_scorecard`: the bottom-line dollar figure, the carrier price
positions, and the routing actions.
