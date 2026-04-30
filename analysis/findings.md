# NYC Subway Safety Crisis: Data Findings & Narrative
**CUNY AI Innovation Hackathon 2026**

---

## The Setup

Before COVID hit, the NYC subway moved about **4.4 million people per day**. It was crowded, sometimes dirty, occasionally crime-ridden — but functional. Then March 2020 happened.

What followed wasn't just a temporary disruption. The data shows a system that collapsed, partially recovered, and is now dealing with a safety environment significantly worse than 2019 — while still running at a fraction of its original capacity.

---

## Finding 1: The Comeback That Isn't Complete

**Ridership never came back.**

At the worst point — April 12, 2020 — only **198,399 people** rode the subway. That's a **95.5% collapse** from the pre-pandemic daily average. It felt like a ghost town underground.

By 2024, ridership recovered to an average of **3.26 million per day**. That sounds like progress — until you realize it's only **72% of pre-pandemic levels**, five years later.

| Year | Avg Daily Ridership | % of Pre-Pandemic |
|------|-------------------|-------------------|
| 2020 | ~1.1M (depressed) | 26.3% |
| 2021 | ~2.0M             | 46.4% |
| 2022 | ~2.7M             | 61.3% |
| 2023 | ~3.1M             | 70.0% |
| 2024 | ~3.3M             | 72.4% |

**Implication:** Remote work permanently shifted behavior. The MTA is collecting less fare revenue — which directly limits its ability to invest in safety, maintenance, and staffing.

---

## Finding 2: Crime Exploded As Riders Came Back

**Transit crime tripled in four years.**

In 2020, the subway recorded 7,252 reported incidents. By 2024, that number hit **26,818** — a **270% increase** while ridership only recovered 72%.

The math is damning: crime grew **3.7x faster than ridership**.

| Year | Total Incidents | Felonies | Misdemeanors |
|------|----------------|----------|--------------|
| 2020 | 7,252          | 3,032    | 3,247        |
| 2021 | 8,879          | 3,270    | 4,529        |
| 2022 | 11,243         | 4,154    | 5,556        |
| 2023 | 14,780         | 4,782    | 7,815        |
| 2024 | 26,818         | 5,007    | 18,825       |

Felony counts grew 65% from 2020 to 2024. But the most alarming number is 2024's misdemeanor explosion — **18,825 misdemeanors**, more than double 2023's count.

### What Crimes Are Happening?

The top felonies in the system (2020–2024 combined):

1. **Grand Larceny** — 5,015 incidents (phone theft, pickpocketing)
2. **Criminal Mischief** — 4,316 (vandalism, graffiti, property destruction)
3. **Robbery** — 2,703 (direct theft with force or threat)
4. **Felony Assault** — 2,533 (the pushing and attack incidents that made national headlines)
5. **Dangerous Weapons** — 1,795 (weapons possession — knives, guns)

The felony assault number is the one that matters most to public perception. These are the incidents — people pushed onto tracks, random attacks at 2am — that drove riders away and made national news in 2022 and 2023.

### Where?

| Borough   | Felony Incidents (2020–2024) |
|-----------|------------------------------|
| Manhattan | 8,101                        |
| Brooklyn  | 5,248                        |
| Bronx     | 3,638                        |
| Queens    | 3,214                        |

Manhattan leads in raw volume because it has the most stations and transfers. But the **Bronx has the highest felony-to-total-crime ratio** — meaning when crimes happen there, they're more likely to be serious.

---

## Finding 3: The Infrastructure Is Quietly Failing

**While everyone watched crime stats, elevators were trapping people.**

Over 2020–2025, the subway recorded:
- **145,150 unscheduled outages** — elevators and escalators failing without warning
- **6,595 entrapments** — riders physically trapped inside broken elevators

Worse: entrapments are **getting worse every year**, not better.

| Year | Unscheduled Outages | Entrapments |
|------|--------------------|-|
| 2020 | 19,963             | 925  |
| 2021 | 24,568             | 1,001 |
| 2022 | 25,915             | 1,090 |
| 2023 | 24,991             | 1,138 |
| 2024 | 25,906             | 1,173 |
| 2025 | 23,807             | 1,268 |

That's a **37% increase in entrapments** since 2020, even as the MTA invested billions in capital programs. The equipment is aging faster than it's being replaced.

### The Worst Stations

The stations with the most unscheduled outages are the ones riders can least afford to have fail:

1. **34th St–Herald Sq** — 8,389 unscheduled outages
2. **34th St–Hudson Yards** — 7,493
3. **Grand Central–42nd St** — 5,069
4. **Bowling Green** — 4,780
5. **Lexington Av/63rd St** — 4,495

These are major transfer hubs. A broken elevator here doesn't just inconvenience one rider — it ripples across thousands.

---

## The Core Argument

The NYC subway is caught in a **compounding safety crisis** driven by three forces that reinforce each other:

**Revenue decline → Deferred maintenance → Infrastructure failure → Rider fear → Lower ridership → Less revenue**

And layered on top: a post-pandemic environment where crime flourished in under-occupied, under-staffed stations.

The system isn't failing because one thing went wrong. It's failing because multiple stressors hit simultaneously and none of them have been fully addressed.

---

## What the Data Doesn't Show (But We Should Acknowledge)

- **Fare evasion** — MTA estimates $700M+ in annual lost revenue; we don't have 2020–2025 granular data but this directly funds the revenue problem above
- **Homeless population / EDP incidents** — No clean dataset available for this analysis, but NYPD Transit Bureau EDP calls surged post-2020
- **Worker safety incidents** — Separate from rider safety; not included here
- **Near-miss events / track intrusions** — MTA tracks this internally but it's not consistently published

---

## Recommendations (For the Hackathon Pitch)

1. **Dynamic police deployment** — Use crime heatmaps (borough + time of day) to allocate Transit Bureau resources where incidents are clustering, not fixed patrols
2. **Predictive elevator maintenance** — Entrapment data + outage frequency → ML model to flag equipment before failure, prioritizing high-traffic stations
3. **Real-time safety transparency** — A public-facing dashboard showing live crime reports and elevator status, so riders can make informed decisions and pressure points become visible
4. **Ride recovery as a safety metric** — Track ridership recovery as a leading indicator of perceived safety; set a target (90% of pre-pandemic) and measure interventions against it

---

*Data Sources: MTA Daily Ridership (data.ny.gov), NYPD Complaint Data (data.cityofnewyork.us), MTA NYCT Elevator & Escalator Availability (data.ny.gov)*
