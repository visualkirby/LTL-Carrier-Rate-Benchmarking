# LTL Lane Rate Benchmarking — Findings

Sawandi Kirby · Sample: 1,024 LTL shipment quotes, 12 lanes, 5 carriers, Jan–Dec 2025

## Bottom line

Linehaul spend above the lane benchmark totals $7,759 across 6 carrier-lane pairs. BlueRidge LTL is four of the six and about $6,100 of it. The fix is routing discipline on 5 lanes. No rate negotiation needed.

## Method

Each quote's linehaul rate (cost per hundredweight, before fuel and accessorials) was measured against the median rate for the same lane and freight-class band, computed from the other four carriers so no carrier is scored against a benchmark it helped set. A carrier-lane more than one standard deviation above market (rate index over 110) is flagged.

## Carrier price position (100 = market)

| Carrier | Median index | Consistency (IQR) | Lanes served |
|---|---|---|---|
| Palmetto Freight Systems | 92 | wide, 34 | 9 |
| Piedmont Freight Line | 93 | tight, 28 | 10 |
| Cardinal Motor Freight | 100 | 31 | 9 |
| BlueRidge LTL | 105 | 33 | 12 |
| Crossroads Freight Co | 107 | 32 | 9 |

Piedmont and Palmetto sit about 8% below market. Palmetto is a touch cheaper but its quotes swing wider, so Piedmont is the more dependable primary.

## Flagged carrier-lanes

| Lane | Carrier | Index | Excess linehaul | Note |
|---|---|---|---|---|
| CLT-RIC | BlueRidge LTL | 126 | $2,943 | currently the backup carrier |
| DFW-ATL | BlueRidge LTL | 116 | $1,980 | high volume |
| CLT-ATL | Cardinal Motor Freight | 114 | $1,776 | high volume |
| ATL-EWR | BlueRidge LTL | 114 | $731 | |
| GSO-BNA | BlueRidge LTL | 126 | $448 | thin data, 9 quotes |
| ATL-MCO | Crossroads Freight Co | 115 | -$119 | net neutral on dollars |

## Recommended actions

1. CLT-RIC: route to Piedmont (primary, index 79). Drop BlueRidge as backup.
2. DFW-ATL and CLT-ATL: shift volume off BlueRidge and Cardinal to each lane's primary. Biggest recovery.
3. ATL-EWR: minor, handle at the next quarterly review.
4. GSO-BNA: get more quotes before acting.
5. ATL-MCO / Crossroads: no action, flagged on rate but dollar-neutral.

## Caveats

- 8 of 48 lane-class cells have under 10 quotes. Benchmarks there are directional.
- JFK-BOS has no reliable primary. Piedmont looks cheapest but on 5 quotes.
- Linehaul rate only. Fuel and accessorials are excluded since they aren't carrier-negotiable the same way.
