# LTL Domain Mechanics Reference

Grounding notes for the LTL Carrier Rate Benchmarking case study (Session 1 checkpoint 4). These are the three mechanics the synthetic dataset is built against, each cited to a real source.

## Freight Class (NMFC)

The National Motor Freight Classification (NMFC) is the standard the LTL industry uses to price commodities. It's developed and published by the National Motor Freight Traffic Association (NMFTA), a nonprofit that's represented the LTL carrier industry since 1956. Every commodity gets assigned one of 18 classes, ranging from class 50 to class 500.

Classification runs on four factors: density, stowability, handling, and liability. Density carries the most weight in practice — it measures how much space an item takes up relative to how much it weighs. Denser freight (more weight per cubic foot) gets a lower class and a cheaper rate; less dense freight (bulky, light) gets a higher class and a more expensive rate, because it takes up trailer space without contributing proportional revenue.

Density calculation:
1. Length × width × height, in inches, divided by 1,728 → cubic feet.
2. Total shipment weight (including packaging) ÷ cubic feet → density in lbs/ft³.

Source: [NMFTA — Classification](https://nmfta.org/standards/classification/nmfc/), [ODFL Density Calculator](https://www.odfl.com/us/en/tools/other-tools/density-calculator.html)

## Weight Breaks (CWT)

LTL rates are quoted per hundredweight (CWT — "centum weight"): take the shipment weight, divide by 100, multiply by the CWT rate for that lane and class. Carriers publish weight-break tiers, and the CWT rate drops at each tier as shipment weight increases — roughly under 500 lbs, 500-999, 1,000-1,999, 2,000-4,999, and 5,000+ lbs, though exact breakpoints vary by carrier.

The counterintuitive part: shipping more weight can sometimes cost less total, because crossing into the next tier drops the per-CWT rate enough to offset the added pounds. A shipment sitting just under a weight break is a real case where declaring the extra weight (or consolidating with another shipment) lowers the total charge.

Source: [Translogistics — CWT in LTL Shipping](https://www.translogisticsinc.com/blog/cwt-ltl)

## Accessorial Charges

Accessorials are fees for anything outside standard dock-to-dock service. The most common:

- **Liftgate** — required when the pickup or delivery location has no loading dock ($75-200+ per shipment).
- **Residential delivery/pickup** — applies when the address isn't a commercial "business zone" location with set public hours.
- **Inside delivery** — moving freight past the truck/dock into the building.
- **Limited/restricted access** — sites like construction zones, schools, or military bases that require special handling to enter.
- **Detention** — the truck waiting beyond the free time allotted for loading/unloading.
- **Redelivery** — a second delivery attempt after a failed first one.

Accessorials can add 20-40% on top of the base rate, and most of them are avoidable with accurate shipment details declared at tender (the point of booking) rather than discovered at delivery.

Source: [PartnerShip — Accessorial Fees Guide](https://www.partnership.com/free-white-paper-on-freight-accessorial-fees-the-complete-guide)
