"""
LTL Carrier Rate Benchmarking -- synthetic dataset generator.

Rates are built from real LTL rating mechanics (distance, NMFC class, weight-break
tier, fuel surcharge, accessorials), not arbitrary numbers -- see
LTL_Domain_Mechanics.md for the sourced explanation of each mechanic.

Per-carrier market_factor and variance simulate the real fact that carriers don't
quote identically on the same lane; that natural spread is what the rate-
benchmarking analysis measures. Carrier lane footprints vary too -- each carrier
is strong on some lanes, light on others, absent on a few -- so the carrier-
selection analysis has a real coverage-vs-price tradeoff to work with.

Output is a small star schema, matching how a freight analyst's reporting layer
is actually structured:
  fact_shipments.csv     -- one row per quoted shipment
  dim_lanes.csv          -- lane attributes (origin, dest, distance)
  dim_carriers.csv       -- carrier list + SCAC
  dim_nmfc_classes.csv   -- NMFC class reference (density bands, example commodity)
  dim_weight_breaks.csv  -- weight-break tier definitions

The generating parameters (market_factor, variance, class multipliers, tier
factors) are deliberately NOT written to any dimension file. A real analyst
discovers carrier pricing position from the data; handing over the answer key
would make the analysis circular.

A denormalized ltl_shipment_quotes.csv is also written for the Excel side.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

LANES = [
    {"lane_id": "CLT-ATL", "origin_city": "Charlotte", "origin_state": "NC", "dest_city": "Atlanta", "dest_state": "GA", "distance_miles": 245},
    {"lane_id": "CLT-RIC", "origin_city": "Charlotte", "origin_state": "NC", "dest_city": "Richmond", "dest_state": "VA", "distance_miles": 290},
    {"lane_id": "GSO-BNA", "origin_city": "Greensboro", "origin_state": "NC", "dest_city": "Nashville", "dest_state": "TN", "distance_miles": 420},
    {"lane_id": "ATL-MCO", "origin_city": "Atlanta", "origin_state": "GA", "dest_city": "Orlando", "dest_state": "FL", "distance_miles": 440},
    {"lane_id": "CLT-CMH", "origin_city": "Charlotte", "origin_state": "NC", "dest_city": "Columbus", "dest_state": "OH", "distance_miles": 430},
    {"lane_id": "ATL-EWR", "origin_city": "Atlanta", "origin_state": "GA", "dest_city": "Newark", "dest_state": "NJ", "distance_miles": 850},
    {"lane_id": "ORD-CLT", "origin_city": "Chicago", "origin_state": "IL", "dest_city": "Charlotte", "dest_state": "NC", "distance_miles": 750},
    {"lane_id": "DFW-ATL", "origin_city": "Dallas", "origin_state": "TX", "dest_city": "Atlanta", "dest_state": "GA", "distance_miles": 780},
    {"lane_id": "ORD-DFW", "origin_city": "Chicago", "origin_state": "IL", "dest_city": "Dallas", "dest_state": "TX", "distance_miles": 925},
    {"lane_id": "LAX-PHX", "origin_city": "Los Angeles", "origin_state": "CA", "dest_city": "Phoenix", "dest_state": "AZ", "distance_miles": 370},
    {"lane_id": "DFW-IAH", "origin_city": "Dallas", "origin_state": "TX", "dest_city": "Houston", "dest_state": "TX", "distance_miles": 240},
    {"lane_id": "JFK-BOS", "origin_city": "New York", "origin_state": "NY", "dest_city": "Boston", "dest_state": "MA", "distance_miles": 215},
]

# market_factor: systematic pricing position relative to baseline (1.0).
# variance: how tightly/loosely a carrier's quotes cluster (std dev as a fraction of rate).
# scac: Standard Carrier Alpha Code, the real industry carrier identifier.
CARRIERS = {
    "Piedmont Freight Line":    {"market_factor": 0.95, "variance": 0.05, "scac": "PDMF"},
    "Cardinal Motor Freight":   {"market_factor": 1.00, "variance": 0.07, "scac": "CDMF"},
    "BlueRidge LTL":            {"market_factor": 1.08, "variance": 0.06, "scac": "BLRG"},
    "Palmetto Freight Systems": {"market_factor": 0.98, "variance": 0.12, "scac": "PLFS"},
    "Crossroads Freight Co":    {"market_factor": 1.03, "variance": 0.08, "scac": "CRFC"},
}

# NMFC class -> relative rate multiplier. Higher class (lower density) costs more
# per CWT -- see LTL_Domain_Mechanics.md. Multiplier stays internal to the
# generator; only the class number and its density band ship in the dim.
NMFC_CLASSES = {
    50:   {"mult": 0.75, "density_band": "over 50 pcf",   "example": "Bricks, ceramic tile, flooring"},
    55:   {"mult": 0.80, "density_band": "35-50 pcf",     "example": "Bagged cement, hardwood flooring"},
    60:   {"mult": 0.85, "density_band": "30-35 pcf",     "example": "Car parts, steel cable"},
    65:   {"mult": 0.90, "density_band": "22.5-30 pcf",   "example": "Bottled beverages, books, car accessories"},
    70:   {"mult": 0.95, "density_band": "15-22.5 pcf",   "example": "Auto engines, packaged food"},
    77.5: {"mult": 1.00, "density_band": "13.5-15 pcf",   "example": "Tires, bathroom fixtures"},
    85:   {"mult": 1.08, "density_band": "12-13.5 pcf",   "example": "Crated machinery, cast-iron pipe"},
    92.5: {"mult": 1.15, "density_band": "10.5-12 pcf",   "example": "Computers, monitors, assembled furniture"},
    100:  {"mult": 1.25, "density_band": "9-10.5 pcf",    "example": "Boat covers, car covers, canvas"},
    110:  {"mult": 1.35, "density_band": "8-9 pcf",       "example": "Cabinets, framed pictures"},
    125:  {"mult": 1.50, "density_band": "7-8 pcf",       "example": "Small household appliances"},
    150:  {"mult": 1.70, "density_band": "6-7 pcf",       "example": "Auto sheet metal, bookcases"},
    175:  {"mult": 1.90, "density_band": "5-6 pcf",       "example": "Clothing, upholstered furniture"},
    200:  {"mult": 2.10, "density_band": "4-5 pcf",       "example": "Aircraft parts, aluminum tables"},
    250:  {"mult": 2.40, "density_band": "3-4 pcf",       "example": "Bamboo furniture, mattresses, plasma TVs"},
}

# Weight-break tiers: heavier shipments get a lower per-CWT rate. Ranges are
# public rating knowledge; the tier_factor stays internal to the generator.
WEIGHT_BREAKS = [
    {"tier": "L5C", "min_lbs": 0,    "max_lbs": 499,    "factor": 1.30, "label": "Under 500 lb"},
    {"tier": "M5C", "min_lbs": 500,  "max_lbs": 999,    "factor": 1.15, "label": "500-999 lb"},
    {"tier": "1M",  "min_lbs": 1000, "max_lbs": 1999,   "factor": 1.00, "label": "1,000-1,999 lb"},
    {"tier": "2M",  "min_lbs": 2000, "max_lbs": 4999,   "factor": 0.85, "label": "2,000-4,999 lb"},
    {"tier": "5M",  "min_lbs": 5000, "max_lbs": 999999, "factor": 0.70, "label": "5,000 lb and up"},
]


def weight_break_for(weight):
    for wb in WEIGHT_BREAKS:
        if wb["min_lbs"] <= weight <= wb["max_lbs"]:
            return wb["tier"], wb["factor"]
    return WEIGHT_BREAKS[-1]["tier"], WEIGHT_BREAKS[-1]["factor"]


def base_cwt_rate(distance_miles):
    """Longer hauls carry a lower per-CWT baseline (linehaul efficiency)."""
    if distance_miles < 300:
        return 28.50
    elif distance_miles < 800:
        return 22.00
    else:
        return 17.50


# name -> (probability applied, flat fee)
ACCESSORIALS = {
    "liftgate":        (0.12, 95),
    "residential":     (0.10, 110),
    "inside_delivery": (0.06, 150),
    "limited_access":  (0.05, 85),
}

FUEL_SURCHARGE_PCT = 0.22  # applied to linehaul, realistic current FSC range


# --- Carrier lane footprints -------------------------------------------------
# Each carrier is strong on some lanes, light on others, absent on a couple.
# Guaranteed: every lane keeps at least 3 carriers so benchmarks stay possible.
lane_ids = [ln["lane_id"] for ln in LANES]
carrier_names = list(CARRIERS.keys())

footprint = {}  # (carrier, lane) -> "strong" | "light" | "none"
for c in carrier_names:
    shuffled = list(np.random.permutation(lane_ids))
    n_strong = int(np.random.randint(3, 8))   # 3-7 lanes this carrier competes hard on
    n_none = int(np.random.randint(0, 5))     # 0-4 lanes this carrier doesn't serve
    strong = set(shuffled[:n_strong])
    none_lanes = set(shuffled[len(shuffled) - n_none:]) if n_none else set()
    for ln in lane_ids:
        if ln in strong:
            footprint[(c, ln)] = "strong"
        elif ln in none_lanes:
            footprint[(c, ln)] = "none"
        else:
            footprint[(c, ln)] = "light"

# Guard: any lane with fewer than 3 serving carriers gets its dropped carriers
# restored to "light" until it has 3.
for ln in lane_ids:
    serving = [c for c in carrier_names if footprint[(c, ln)] != "none"]
    if len(serving) < 3:
        dropped = [c for c in carrier_names if footprint[(c, ln)] == "none"]
        for c in dropped[: 3 - len(serving)]:
            footprint[(c, ln)] = "light"

VOLUME = {"strong": (24, 36), "light": (5, 12), "none": (0, 0)}
# ---------------------------------------------------------------------------

records = []
shipment_id = 1
start_date = datetime(2025, 1, 1)

for lane in LANES:
    for carrier_name, carrier in CARRIERS.items():
        lo, hi = VOLUME[footprint[(carrier_name, lane["lane_id"])]]
        n_quotes = 0 if hi == 0 else int(np.random.randint(lo, hi + 1))
        for _ in range(n_quotes):
            nmfc_class = np.random.choice(list(NMFC_CLASSES.keys()))
            weight = int(np.random.uniform(150, 8000))
            tier, tier_factor = weight_break_for(weight)

            cwt = base_cwt_rate(lane["distance_miles"]) * NMFC_CLASSES[nmfc_class]["mult"] * tier_factor
            carrier_noise = np.random.normal(1.0, carrier["variance"])
            cwt_final = max(cwt * carrier["market_factor"] * carrier_noise, 1.0)

            linehaul = (weight / 100) * cwt_final

            accessorial_list = []
            accessorial_total = 0
            for name, (prob, fee) in ACCESSORIALS.items():
                if np.random.random() < prob:
                    accessorial_list.append(name)
                    accessorial_total += fee

            fuel_surcharge = linehaul * FUEL_SURCHARGE_PCT
            quoted_total = round(linehaul + fuel_surcharge + accessorial_total, 2)
            quote_date = start_date + timedelta(days=int(np.random.uniform(0, 365)))

            records.append({
                "shipment_id": f"S{shipment_id:05d}",
                "quote_date": quote_date.strftime("%Y-%m-%d"),
                "lane_id": lane["lane_id"],
                "carrier_name": carrier_name,
                "nmfc_class": nmfc_class,
                "weight_lbs": weight,
                "weight_break_tier": tier,
                "base_cwt_rate": round(cwt_final, 2),
                "accessorials": ";".join(accessorial_list) if accessorial_list else "none",
                "accessorial_total": accessorial_total,
                "fuel_surcharge": round(fuel_surcharge, 2),
                "quoted_rate_total": quoted_total,
            })
            shipment_id += 1

fact = pd.DataFrame(records).sort_values(["lane_id", "quote_date", "shipment_id"]).reset_index(drop=True)

dim_lanes = pd.DataFrame(LANES)

dim_carriers = pd.DataFrame(
    [{"carrier_name": name, "scac": c["scac"]} for name, c in CARRIERS.items()]
)

dim_nmfc = pd.DataFrame(
    [{"nmfc_class": k, "density_band": v["density_band"], "example_commodity": v["example"]}
     for k, v in NMFC_CLASSES.items()]
)

dim_weight_breaks = pd.DataFrame(
    [{"weight_break_tier": w["tier"], "min_weight_lbs": w["min_lbs"],
      "max_weight_lbs": w["max_lbs"], "tier_label": w["label"]}
     for w in WEIGHT_BREAKS]
)

# Star schema files
fact.to_csv("fact_shipments.csv", index=False)
dim_lanes.to_csv("dim_lanes.csv", index=False)
dim_carriers.to_csv("dim_carriers.csv", index=False)
dim_nmfc.to_csv("dim_nmfc_classes.csv", index=False)
dim_weight_breaks.to_csv("dim_weight_breaks.csv", index=False)

# Denormalized extract for the Excel side
denorm = (
    fact.merge(dim_lanes, on="lane_id", how="left")
        .merge(dim_carriers, on="carrier_name", how="left")
)
denorm.to_csv("ltl_shipment_quotes.csv", index=False)

# --- Validation ------------------------------------------------------------
recomputed = (
    fact["base_cwt_rate"] * fact["weight_lbs"] / 100
    + fact["fuel_surcharge"]
    + fact["accessorial_total"]
).round(2)
max_diff = (recomputed - fact["quoted_rate_total"]).abs().max()

lane_carrier_cov = (
    fact.groupby("lane_id")["carrier_name"].nunique().rename("carriers_serving")
)

print(f"fact_shipments: {len(fact)} rows across {fact['lane_id'].nunique()} lanes "
      f"and {fact['carrier_name'].nunique()} carriers")
print(f"rate identity max rounding diff: ${max_diff:.2f}")
print(f"carriers serving each lane: min {lane_carrier_cov.min()}, max {lane_carrier_cov.max()}")
print("\ncarrier lane coverage (lanes served of 12):")
print(fact.groupby("carrier_name")["lane_id"].nunique().to_string())
