"""
analyze.py
Full analysis and chart generation for NYC Subway Safety 2020–2025
Outputs all charts to charts/
"""

import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings("ignore")

BASE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN  = os.path.join(BASE, "data", "clean")
CHARTS = os.path.join(BASE, "charts")

# ── Style ──────────────────────────────────────────────────────────────────────
PALETTE  = ["#1a1a2e", "#16213e", "#0f3460", "#e94560", "#f5a623", "#2ecc71"]
BG       = "#0d1117"
GRID_CLR = "#21262d"
TEXT_CLR = "#e6edf3"
ACCENT   = "#e94560"
SAFE_GRN = "#2ecc71"
WARN_ORG = "#f5a623"
MTA_BLUE = "#0039a6"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor":   BG,
    "axes.edgecolor":   GRID_CLR,
    "axes.labelcolor":  TEXT_CLR,
    "xtick.color":      TEXT_CLR,
    "ytick.color":      TEXT_CLR,
    "text.color":       TEXT_CLR,
    "grid.color":       GRID_CLR,
    "grid.linestyle":   "--",
    "grid.alpha":       0.5,
    "font.family":      "DejaVu Sans",
    "font.size":        11,
    "axes.titlesize":   14,
    "axes.titleweight": "bold",
    "legend.facecolor": "#161b22",
    "legend.edgecolor": GRID_CLR,
})


def save(name):
    path = os.path.join(CHARTS, name)
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"  ✓ {name}")


def main():
    os.makedirs(CHARTS, exist_ok=True)

    # ── Load clean data ────────────────────────────────────────────────────────
    print("Loading cleaned data...")
    ride  = pd.read_csv(os.path.join(CLEAN, "ridership_clean.csv"), parse_dates=["date"])
    crime = pd.read_csv(os.path.join(CLEAN, "crime_clean.csv"),     parse_dates=["date"])
    elev  = pd.read_csv(os.path.join(CLEAN, "elevator_clean.csv"),  parse_dates=["month"])

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 1 — Ridership Recovery 2020–2025
    # ══════════════════════════════════════════════════════════════════════════
    print("\nChart 1: Ridership recovery...")

    ride_col = [c for c in ride.columns if "subway" in c and "ridership" in c][0]
    pct_col  = [c for c in ride.columns if "subway" in c and "pct" in c][0]

    fig, ax1 = plt.subplots(figsize=(14, 6))

    ride_sorted = ride.sort_values("date")
    rolling = ride_sorted[ride_col].rolling(30).mean()

    ax1.fill_between(ride_sorted["date"], rolling / 1e6, alpha=0.3, color=MTA_BLUE)
    ax1.plot(ride_sorted["date"], rolling / 1e6, color=MTA_BLUE, linewidth=2, label="30-day avg ridership")
    ax1.scatter(ride_sorted["date"], ride_sorted[ride_col] / 1e6,
                color=MTA_BLUE, alpha=0.15, s=4)

    events = {
        "Mar 2020\nLockdown":  "2020-03-22",
        "Jun 2021\nReopening": "2021-06-15",
        "2022 Crime\nSpike":   "2022-04-01",
    }
    for label, dt in events.items():
        x = pd.to_datetime(dt)
        ax1.axvline(x, color=ACCENT, linestyle=":", alpha=0.8, linewidth=1.2)
        ax1.text(x, ax1.get_ylim()[1] if ax1.get_ylim()[1] > 0 else 4,
                 label, color=ACCENT, fontsize=8, ha="center", va="top",
                 bbox=dict(boxstyle="round,pad=0.2", facecolor=BG, edgecolor=ACCENT, alpha=0.8))

    ax1.set_ylabel("Riders (millions)", color=TEXT_CLR)
    ax1.set_xlabel("")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}M"))
    ax1.set_ylim(bottom=0)
    ax1.set_title("NYC Subway Ridership Recovery: March 2020 – Jan 2025\n"
                  "The pandemic collapse — and an incomplete comeback", pad=15)
    ax1.grid(axis="y")
    ax1.legend(loc="upper left")
    fig.tight_layout()
    save("01_ridership_recovery.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 2 — Annual Crime Totals by Category
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 2: Annual crime by category...")

    cat_map = {"FELONY": "Felony", "MISDEMEANOR": "Misdemeanor", "VIOLATION": "Violation"}
    crime_filtered = crime[crime["law_cat_cd"].isin(cat_map.keys())].copy()
    crime_filtered["category"] = crime_filtered["law_cat_cd"].map(cat_map)

    annual_cat = crime_filtered.groupby(["year", "category"]).size().reset_index(name="count")

    years = sorted(annual_cat["year"].unique())
    cats  = ["Felony", "Misdemeanor", "Violation"]
    cat_colors = {"Felony": ACCENT, "Misdemeanor": WARN_ORG, "Violation": SAFE_GRN}

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(years))
    width = 0.28
    for i, cat in enumerate(cats):
        vals = [annual_cat[(annual_cat["year"] == y) & (annual_cat["category"] == cat)]["count"].sum()
                for y in years]
        bars = ax.bar(x + (i - 1) * width, vals, width, label=cat,
                      color=cat_colors[cat], alpha=0.9, edgecolor=BG, linewidth=0.5)
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 50,
                        f"{v:,}", ha="center", va="bottom", fontsize=8, color=TEXT_CLR)

    ax.set_xticks(x)
    ax.set_xticklabels(years)
    ax.set_ylabel("Number of Incidents")
    ax.set_title("NYC Subway Crime by Category: 2020–2024\n"
                 "Felonies and misdemeanors climbed sharply after 2020", pad=15)
    ax.legend()
    ax.grid(axis="y")
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    save("02_annual_crime_by_category.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 3 — Top 10 Offense Types (Felonies only)
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 3: Top offense types...")

    felonies = crime[crime["law_cat_cd"] == "FELONY"].copy()
    top_offenses = felonies.groupby("ofns_desc").size().sort_values(ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(range(len(top_offenses)), top_offenses.values,
                   color=[ACCENT if i == 0 else "#0f3460" for i in range(len(top_offenses))],
                   edgecolor=BG, linewidth=0.5, alpha=0.92)
    ax.set_yticks(range(len(top_offenses)))
    ax.set_yticklabels([o.title()[:45] for o in top_offenses.index], fontsize=10)
    ax.invert_yaxis()

    for bar, val in zip(bars, top_offenses.values):
        ax.text(val + 20, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=9, color=TEXT_CLR)

    ax.set_xlabel("Total Incidents (2020–2024)")
    ax.set_title("Top 10 Felony Offense Types in NYC Subway: 2020–2024\n"
                 "Grand larceny and assault drive the headline numbers", pad=15)
    ax.grid(axis="x")
    ax.set_xlim(right=top_offenses.values[0] * 1.15)
    fig.tight_layout()
    save("03_top_felony_offenses.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 4 — Crime Trend Over Time (Monthly)
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 4: Monthly crime trend...")

    monthly_crime = crime_filtered.groupby(["month_year", "category"]).size().reset_index(name="count")
    monthly_crime["date"] = pd.to_datetime(monthly_crime["month_year"])
    monthly_crime = monthly_crime.sort_values("date")

    fig, ax = plt.subplots(figsize=(14, 6))
    for cat in cats:
        sub = monthly_crime[monthly_crime["category"] == cat]
        ax.plot(sub["date"], sub["count"], color=cat_colors[cat],
                linewidth=1.5, label=cat, alpha=0.85)
        ax.fill_between(sub["date"], sub["count"], alpha=0.08, color=cat_colors[cat])

    ax.axvline(pd.to_datetime("2022-01-01"), color="white", linestyle=":", alpha=0.5, linewidth=1)
    ax.text(pd.to_datetime("2022-01-01"), ax.get_ylim()[1] * 0.95 if ax.get_ylim()[1] > 0 else 500,
            "2022 surge", color="white", fontsize=8, ha="left",
            bbox=dict(boxstyle="round,pad=0.2", facecolor=BG, edgecolor="white", alpha=0.6))

    ax.set_ylabel("Incidents per Month")
    ax.set_title("Monthly Transit Crime Trend: 2020–2024\n"
                 "Misdemeanors dominate volume; felonies show alarming 2022 spike", pad=15)
    ax.legend()
    ax.grid(axis="y")
    fig.tight_layout()
    save("04_monthly_crime_trend.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 5 — Crime by Borough
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 5: Crime by borough...")

    boro_crime = (
        crime_filtered[
            crime_filtered["boro_nm"].notna()
            & (crime_filtered["boro_nm"] != "NAN")
            & (crime_filtered["boro_nm"] != "")
        ]
        .groupby(["boro_nm", "category"])
        .size()
        .reset_index(name="count")
    )

    boroughs  = boro_crime.groupby("boro_nm")["count"].sum().sort_values(ascending=False).index.tolist()
    boro_crime = boro_crime[boro_crime["boro_nm"].isin(boroughs)]

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(boroughs))
    for i, cat in enumerate(cats):
        vals = [boro_crime[(boro_crime["boro_nm"] == b) & (boro_crime["category"] == cat)]["count"].sum()
                for b in boroughs]
        ax.bar(x + (i - 1) * 0.28, vals, 0.28, label=cat,
               color=cat_colors[cat], alpha=0.9, edgecolor=BG)

    ax.set_xticks(x)
    ax.set_xticklabels([b.title() for b in boroughs], fontsize=11)
    ax.set_ylabel("Total Incidents (2020–2024)")
    ax.set_title("Subway Crime by Borough: 2020–2024\n"
                 "Manhattan leads in volume — but Bronx has the highest felony ratio", pad=15)
    ax.legend()
    ax.grid(axis="y")
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    save("05_crime_by_borough.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 6 — Elevator / Escalator Unscheduled Outages Over Time
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 6: Elevator outages over time...")

    elev_col_names = elev.columns.tolist()
    unsch_col = [c for c in elev_col_names if "unscheduled" in c]
    entrap_col = [c for c in elev_col_names if "entrapment" in c]
    equip_col  = [c for c in elev_col_names if "equipment_type" in c]

    if unsch_col and equip_col:
        unsch_col = unsch_col[0]
        equip_col = equip_col[0]

        monthly_outages = elev.groupby(["month", equip_col])[unsch_col].sum().reset_index()
        monthly_outages.columns = ["month", "equipment_type", "unscheduled_outages"]

        fig, ax = plt.subplots(figsize=(14, 6))
        for eq, color in [("Elevator", WARN_ORG), ("Escalator", "#3498db")]:
            sub = monthly_outages[monthly_outages["equipment_type"] == eq]
            if len(sub) > 0:
                ax.plot(sub["month"], sub["unscheduled_outages"],
                        color=color, linewidth=2, label=eq)
                ax.fill_between(sub["month"], sub["unscheduled_outages"],
                                alpha=0.1, color=color)

        ax.set_ylabel("Unscheduled Outages per Month")
        ax.set_title("Subway Elevator & Escalator Unscheduled Outages: 2020–2025\n"
                     "Infrastructure failures that strand riders — especially those with disabilities", pad=15)
        ax.legend()
        ax.grid(axis="y")
        fig.tight_layout()
        save("06_elevator_outages_trend.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 7 — Entrapments per Year
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 7: Entrapments per year...")

    if entrap_col:
        entrap_col = entrap_col[0]
        annual_entrap = elev.groupby("year")[entrap_col].sum().reset_index()
        annual_entrap.columns = ["year", "entrapments"]

        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(annual_entrap["year"].astype(str), annual_entrap["entrapments"],
                      color=[ACCENT if v == annual_entrap["entrapments"].max() else "#0f3460"
                             for v in annual_entrap["entrapments"]],
                      edgecolor=BG, linewidth=0.5, width=0.6, alpha=0.92)

        for bar, val in zip(bars, annual_entrap["entrapments"]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f"{int(val):,}", ha="center", va="bottom", fontsize=10, color=TEXT_CLR)

        ax.set_ylabel("Total Entrapments")
        ax.set_title("Elevator Entrapments in NYC Subway per Year: 2020–2025\n"
                     "Riders physically trapped in failing elevators", pad=15)
        ax.grid(axis="y")
        ax.set_ylim(bottom=0)
        fig.tight_layout()
        save("07_entrapments_per_year.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 8 — Ridership vs. Crime (dual axis overlay)
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 8: Ridership vs crime overlay...")

    ride_monthly = ride.groupby(ride["date"].dt.to_period("M"))[ride_col].mean().reset_index()
    ride_monthly["date"] = ride_monthly["date"].dt.to_timestamp()

    felony_monthly = (
        crime[crime["law_cat_cd"] == "FELONY"]
        .groupby("month_year")
        .size()
        .reset_index(name="felonies")
    )
    felony_monthly["date"] = pd.to_datetime(felony_monthly["month_year"])
    felony_monthly = felony_monthly.sort_values("date")

    merged = pd.merge(ride_monthly, felony_monthly, on="date", how="inner")

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax2 = ax1.twinx()

    ax1.plot(merged["date"], merged[ride_col] / 1e6,
             color=MTA_BLUE, linewidth=2.5, label="Avg Daily Riders")
    ax1.fill_between(merged["date"], merged[ride_col] / 1e6, alpha=0.15, color=MTA_BLUE)

    ax2.plot(merged["date"], merged["felonies"],
             color=ACCENT, linewidth=2.5, linestyle="--", label="Felonies/Month")
    ax2.fill_between(merged["date"], merged["felonies"], alpha=0.1, color=ACCENT)

    ax1.set_ylabel("Avg Daily Subway Riders (M)", color=MTA_BLUE)
    ax2.set_ylabel("Felony Incidents per Month", color=ACCENT)
    ax1.tick_params(axis="y", labelcolor=MTA_BLUE)
    ax2.tick_params(axis="y", labelcolor=ACCENT)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}M"))

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower right")

    ax1.set_title("Ridership Recovery vs. Felony Crime: 2020–2024\n"
                  "Crime surged as riders came back — the safety paradox", pad=15)
    ax1.grid(axis="y")
    fig.tight_layout()
    save("08_ridership_vs_crime.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 9 — % Pre-Pandemic Recovery by Year
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 9: Recovery percentage...")

    pct_annual = ride.groupby("year")[pct_col].mean().reset_index()
    pct_annual.columns = ["year", "avg_pct_recovery"]

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = [ACCENT if v < 70 else WARN_ORG if v < 85 else SAFE_GRN
              for v in pct_annual["avg_pct_recovery"]]
    bars = ax.bar(pct_annual["year"].astype(str), pct_annual["avg_pct_recovery"],
                  color=colors, edgecolor=BG, linewidth=0.5, width=0.6, alpha=0.92)

    ax.axhline(100, color="white", linestyle="--", alpha=0.5, linewidth=1.2, label="Pre-pandemic baseline")
    for bar, val in zip(bars, pct_annual["avg_pct_recovery"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.0f}%", ha="center", va="bottom", fontsize=11, color=TEXT_CLR)

    ax.set_ylabel("% of Pre-Pandemic Ridership")
    ax.set_ylim(0, 115)
    ax.set_title("Subway Ridership as % of Pre-Pandemic Levels: 2020–2024\n"
                 "Five years later, the system still hasn't fully recovered", pad=15)
    ax.legend()
    ax.grid(axis="y")
    fig.tight_layout()
    save("09_recovery_percentage.png")

    # ══════════════════════════════════════════════════════════════════════════
    # CHART 10 — Summary Dashboard (4-panel)
    # ══════════════════════════════════════════════════════════════════════════
    print("Chart 10: Summary dashboard...")

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("NYC Subway Safety Crisis: 2020–2025  |  Key Indicators",
                 fontsize=16, fontweight="bold", color=TEXT_CLR, y=1.01)

    ax = axes[0, 0]
    ax.bar(pct_annual["year"].astype(str), pct_annual["avg_pct_recovery"],
           color=colors, edgecolor=BG, alpha=0.9)
    ax.axhline(100, color="white", linestyle="--", alpha=0.5)
    ax.set_title("Ridership Recovery (%)", color=TEXT_CLR)
    ax.set_ylabel("% of Pre-Pandemic")
    ax.grid(axis="y")
    ax.set_ylim(0, 115)
    for i, (yr, val) in enumerate(zip(pct_annual["year"].astype(str), pct_annual["avg_pct_recovery"])):
        ax.text(i, val + 1, f"{val:.0f}%", ha="center", fontsize=9, color=TEXT_CLR)

    ax = axes[0, 1]
    annual_total = crime_filtered.groupby(["year", "category"]).size().reset_index(name="count")
    for cat in cats:
        sub = annual_total[annual_total["category"] == cat]
        ax.plot(sub["year"], sub["count"], marker="o", color=cat_colors[cat], label=cat, linewidth=2)
    ax.set_title("Crime by Category (Annual)", color=TEXT_CLR)
    ax.set_ylabel("Incidents")
    ax.legend(fontsize=9)
    ax.grid(axis="y")

    ax = axes[1, 0]
    top5 = top_offenses.head(5)
    ax.barh(range(len(top5)), top5.values,
            color=[ACCENT] + ["#0f3460"] * 4, alpha=0.9, edgecolor=BG)
    ax.set_yticks(range(len(top5)))
    ax.set_yticklabels([o.title()[:30] for o in top5.index], fontsize=9)
    ax.invert_yaxis()
    ax.set_title("Top 5 Felony Offenses", color=TEXT_CLR)
    ax.grid(axis="x")

    ax = axes[1, 1]
    if entrap_col:
        ax.bar(annual_entrap["year"].astype(str), annual_entrap["entrapments"],
               color=WARN_ORG, edgecolor=BG, alpha=0.9)
        ax.set_title("Elevator Entrapments per Year", color=TEXT_CLR)
        ax.set_ylabel("Entrapments")
        ax.grid(axis="y")
        for i, (yr, val) in enumerate(zip(annual_entrap["year"].astype(str), annual_entrap["entrapments"])):
            ax.text(i, val + 0.5, f"{int(val)}", ha="center", fontsize=9, color=TEXT_CLR)

    plt.tight_layout()
    save("10_summary_dashboard.png")

    print("\n✅ All 10 charts generated in charts/")


if __name__ == "__main__":
    main()
