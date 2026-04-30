"""
build_excel.py
Creates a professional multi-sheet Excel workbook with data tables and native charts.
"""

import pandas as pd
import numpy as np
import os
from openpyxl import Workbook
from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                              GradientFill)
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule

BASE   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN  = os.path.join(BASE, "data", "clean")
OUT    = os.path.join(BASE, "NYC_Subway_Safety_Analysis.xlsx")

# ── Load data ──────────────────────────────────────────────────────────────────
ride  = pd.read_csv(os.path.join(CLEAN, "ridership_clean.csv"), parse_dates=["date"])
crime = pd.read_csv(os.path.join(CLEAN, "crime_clean.csv"),     parse_dates=["date"])
elev  = pd.read_csv(os.path.join(CLEAN, "elevator_clean.csv"),  parse_dates=["month"])

ride_col   = [c for c in ride.columns if "subway" in c and "ridership" in c][0]
pct_col    = [c for c in ride.columns if "subway" in c and "pct" in c][0]
entrap_col = [c for c in elev.columns if "entrapment" in c][0]
unsch_col  = [c for c in elev.columns if "unscheduled" in c][0]
equip_col  = [c for c in elev.columns if "equipment_type" in c][0]

# ── Color palette ──────────────────────────────────────────────────────────────
NAVY      = "1a1a2e"
DARK_BLUE = "0039a6"
RED       = "e94560"
ORANGE    = "f5a623"
GREEN     = "2ecc71"
WHITE     = "FFFFFF"
LIGHT_BG  = "F2F6FF"
MID_GREY  = "D9E1F2"
DARK_GREY = "4A4A6A"

def bold_fill_font(ws, cell_ref, hex_fill, hex_font=WHITE, bold=True, size=11, center=True):
    c = ws[cell_ref]
    c.font = Font(bold=bold, color=hex_font, size=size, name="Arial")
    c.fill = PatternFill("solid", fgColor=hex_fill)
    if center:
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    return c

def header_row(ws, row, headers, fills, start_col=1):
    for i, (h, f) in enumerate(zip(headers, fills)):
        col = start_col + i
        cell = ws.cell(row=row, column=col, value=h)
        cell.font = Font(bold=True, color=WHITE, size=10, name="Arial")
        cell.fill = PatternFill("solid", fgColor=f)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

def data_row(ws, row, values, bg=None, start_col=1, bold=False, num_fmt=None):
    for i, v in enumerate(values):
        col = start_col + i
        cell = ws.cell(row=row, column=col, value=v)
        cell.font = Font(name="Arial", size=10, bold=bold,
                         color=DARK_GREY if not bold else NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        if bg:
            cell.fill = PatternFill("solid", fgColor=bg)
        if num_fmt and i > 0:
            cell.number_format = num_fmt

def thin_border(ws, min_row, max_row, min_col, max_col):
    thin = Side(style="thin", color="BBBBBB")
    for row in ws.iter_rows(min_row=min_row, max_row=max_row,
                             min_col=min_col, max_col=max_col):
        for cell in row:
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

def set_col_widths(ws, widths):
    for col_letter, w in widths.items():
        ws.column_dimensions[col_letter].width = w


wb = Workbook()

# ══════════════════════════════════════════════════════════════════════════════
# SHEET 1 — DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
dash = wb.active
dash.title = "📊 Dashboard"
dash.sheet_view.showGridLines = False
dash.row_dimensions[1].height = 60
dash.row_dimensions[2].height = 18

# Title banner
dash.merge_cells("A1:H1")
t = dash["A1"]
t.value = "NYC SUBWAY SAFETY CRISIS  |  2020 – 2025"
t.font = Font(bold=True, size=20, color=WHITE, name="Arial")
t.fill = PatternFill("solid", fgColor=NAVY)
t.alignment = Alignment(horizontal="center", vertical="center")

dash.merge_cells("A2:H2")
sub = dash["A2"]
sub.value = "CUNY AI Innovation Hackathon 2026  |  Data: MTA & NYPD Open Data"
sub.font = Font(size=10, color=DARK_GREY, name="Arial", italic=True)
sub.fill = PatternFill("solid", fgColor=MID_GREY)
sub.alignment = Alignment(horizontal="center", vertical="center")

# KPI boxes — Row 4
kpis = [
    ("LOWEST RIDERSHIP DAY",   "198,399",      "Apr 12, 2020",  RED),
    ("2024 RECOVERY RATE",     "72.4%",         "vs. pre-pandemic", ORANGE),
    ("CRIME INCREASE",         "+270%",         "2020 → 2024",   RED),
    ("ELEVATOR ENTRAPMENTS",   "6,595",         "2020 – 2025",   DARK_BLUE),
]
dash.row_dimensions[4].height = 14
dash.row_dimensions[5].height = 40
dash.row_dimensions[6].height = 22
dash.row_dimensions[7].height = 22

for i, (label, val, sub_val, color) in enumerate(kpis):
    col = i * 2 + 1
    cl = get_column_letter(col)
    cr = get_column_letter(col + 1)

    dash.merge_cells(f"{cl}4:{cr}4")
    lc = dash[f"{cl}4"]
    lc.value = label
    lc.font = Font(bold=True, size=8, color=WHITE, name="Arial")
    lc.fill = PatternFill("solid", fgColor=color)
    lc.alignment = Alignment(horizontal="center", vertical="center")

    dash.merge_cells(f"{cl}5:{cr}5")
    vc = dash[f"{cl}5"]
    vc.value = val
    vc.font = Font(bold=True, size=22, color=color, name="Arial")
    vc.alignment = Alignment(horizontal="center", vertical="center")

    dash.merge_cells(f"{cl}6:{cr}6")
    sc = dash[f"{cl}6"]
    sc.value = sub_val
    sc.font = Font(size=9, color=DARK_GREY, name="Arial", italic=True)
    sc.alignment = Alignment(horizontal="center", vertical="center")

# Narrative section
dash.row_dimensions[8].height = 12
dash.merge_cells("A9:H9")
n = dash["A9"]
n.value = "THE STORY"
n.font = Font(bold=True, size=12, color=WHITE, name="Arial")
n.fill = PatternFill("solid", fgColor=DARK_BLUE)
n.alignment = Alignment(horizontal="left", vertical="center", indent=1)
dash.row_dimensions[9].height = 20

stories = [
    ("RIDERSHIP", "Pandemic collapsed ridership by 95%. By 2024, only 72.4% recovered — remote work permanently changed commuting behavior."),
    ("CRIME",     "Transit crime tripled: 7,252 incidents in 2020 → 26,818 in 2024. Crime grew 3.7× faster than ridership returned."),
    ("TOP CRIMES","Grand Larceny (5,015), Criminal Mischief (4,316), Robbery (2,703), Felony Assault (2,533), Dangerous Weapons (1,795)."),
    ("ELEVATORS", "145,150 unscheduled outages and 6,595 entrapments in 5 years. Entrapments growing every year — 925 in 2020 to 1,268 in 2025."),
    ("BOROUGH",   "Manhattan leads in crime volume (8,101 felonies). Bronx has the highest felony ratio relative to total incidents."),
    ("WORST STATIONS","34th St-Herald Sq (8,389 outages), Hudson Yards (7,493), Grand Central (5,069) — busiest hubs failing most often."),
]

for i, (cat, text) in enumerate(stories):
    r = 10 + i
    dash.row_dimensions[r].height = 22
    dash[f"A{r}"].value = cat
    dash[f"A{r}"].font = Font(bold=True, size=9, color=WHITE, name="Arial")
    dash[f"A{r}"].fill = PatternFill("solid", fgColor=NAVY)
    dash[f"A{r}"].alignment = Alignment(horizontal="center", vertical="center")
    dash.merge_cells(f"B{r}:H{r}")
    dash[f"B{r}"].value = text
    dash[f"B{r}"].font = Font(size=9, color=NAVY, name="Arial")
    dash[f"B{r}"].fill = PatternFill("solid", fgColor=LIGHT_BG if i % 2 == 0 else WHITE)
    dash[f"B{r}"].alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    thin = Side(style="thin", color="DDDDDD")
    for col in range(1, 9):
        dash.cell(row=r, column=col).border = Border(
            left=thin, right=thin, top=thin, bottom=thin)

set_col_widths(dash, {
    "A": 16, "B": 16, "C": 16, "D": 16,
    "E": 16, "F": 16, "G": 16, "H": 16
})

# ══════════════════════════════════════════════════════════════════════════════
# SHEET 2 — RIDERSHIP
# ══════════════════════════════════════════════════════════════════════════════
rs = wb.create_sheet("🚇 Ridership")
rs.sheet_view.showGridLines = False

# Title
rs.merge_cells("A1:F1")
rs["A1"].value = "MTA Subway Daily Ridership: 2020 – 2025"
rs["A1"].font = Font(bold=True, size=14, color=WHITE, name="Arial")
rs["A1"].fill = PatternFill("solid", fgColor=DARK_BLUE)
rs["A1"].alignment = Alignment(horizontal="center", vertical="center")
rs.row_dimensions[1].height = 30

# Annual summary table
annual_ride = ride.groupby("year").agg(
    avg_daily=(ride_col, "mean"),
    avg_pct=(pct_col, "mean"),
    total_riders=(ride_col, "sum")
).reset_index()

headers = ["Year", "Avg Daily Riders", "% of Pre-Pandemic", "Total Annual Riders"]
header_row(rs, 3, headers, [NAVY, DARK_BLUE, DARK_BLUE, DARK_BLUE])
rs.row_dimensions[3].height = 22

for i, row in annual_ride.iterrows():
    r = 4 + i
    bg = LIGHT_BG if i % 2 == 0 else WHITE
    rs.row_dimensions[r].height = 18
    rs.cell(r, 1, int(row["year"]))
    rs.cell(r, 2, round(row["avg_daily"]))
    rs.cell(r, 3, round(row["avg_pct"], 1) / 100)
    rs.cell(r, 4, round(row["total_riders"]))
    for col in range(1, 5):
        c = rs.cell(r, col)
        c.font = Font(name="Arial", size=10, color=DARK_GREY)
        c.fill = PatternFill("solid", fgColor=bg)
        c.alignment = Alignment(horizontal="center", vertical="center")
    rs.cell(r, 2).number_format = '#,##0'
    rs.cell(r, 3).number_format = '0.0%'
    rs.cell(r, 4).number_format = '#,##0'

thin_border(rs, 3, 3 + len(annual_ride), 1, 4)

# Chart: % Recovery
chart1 = BarChart()
chart1.type = "col"
chart1.title = "Ridership Recovery: % of Pre-Pandemic Level"
chart1.style = 10
chart1.y_axis.title = "% of Pre-Pandemic"
chart1.x_axis.title = "Year"
chart1.height = 14
chart1.width = 22

years_range = Reference(rs, min_col=1, min_row=4, max_row=3 + len(annual_ride))
pct_range   = Reference(rs, min_col=3, min_row=3, max_row=3 + len(annual_ride))
chart1.add_data(pct_range, titles_from_data=True)
chart1.set_categories(years_range)
chart1.series[0].graphicalProperties.solidFill = DARK_BLUE
rs.add_chart(chart1, "F3")

# Monthly ridership table (summarized)
rs.row_dimensions[12].height = 12
rs.merge_cells("A13:D13")
rs["A13"].value = "Monthly Avg Ridership by Year"
rs["A13"].font = Font(bold=True, size=11, color=WHITE, name="Arial")
rs["A13"].fill = PatternFill("solid", fgColor=NAVY)
rs["A13"].alignment = Alignment(horizontal="center", vertical="center")
rs.row_dimensions[13].height = 22

months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
header_row(rs, 14, ["Month"] + [str(y) for y in sorted(ride["year"].unique())], [NAVY] + [DARK_BLUE]*6)
rs.row_dimensions[14].height = 18

monthly = ride.groupby(["year", "month"])[ride_col].mean().unstack("year")
for i, m in enumerate(range(1, 13)):
    r = 15 + i
    rs.row_dimensions[r].height = 16
    bg = LIGHT_BG if i % 2 == 0 else WHITE
    rs.cell(r, 1, months[i])
    rs.cell(r, 1).font = Font(bold=True, name="Arial", size=10, color=NAVY)
    rs.cell(r, 1).fill = PatternFill("solid", fgColor=MID_GREY)
    rs.cell(r, 1).alignment = Alignment(horizontal="center")
    for j, yr in enumerate(sorted(ride["year"].unique())):
        col = 2 + j
        val = monthly[yr].get(m, None)
        rs.cell(r, col, round(val) if pd.notna(val) else "-")
        rs.cell(r, col).font = Font(name="Arial", size=10, color=DARK_GREY)
        rs.cell(r, col).fill = PatternFill("solid", fgColor=bg)
        rs.cell(r, col).alignment = Alignment(horizontal="center")
        rs.cell(r, col).number_format = '#,##0'

thin_border(rs, 14, 26, 1, 7)
set_col_widths(rs, {"A": 14, "B": 16, "C": 16, "D": 16, "E": 16, "F": 16, "G": 16})

# ══════════════════════════════════════════════════════════════════════════════
# SHEET 3 — CRIME
# ══════════════════════════════════════════════════════════════════════════════
cs = wb.create_sheet("🚨 Crime")
cs.sheet_view.showGridLines = False

cs.merge_cells("A1:G1")
cs["A1"].value = "NYPD Transit Bureau Crime: 2020 – 2024  (All crimes inside subway premises)"
cs["A1"].font = Font(bold=True, size=14, color=WHITE, name="Arial")
cs["A1"].fill = PatternFill("solid", fgColor=RED)
cs["A1"].alignment = Alignment(horizontal="center", vertical="center")
cs.row_dimensions[1].height = 30

# Annual totals by category
crime_cat = crime[crime["law_cat_cd"].isin(["FELONY","MISDEMEANOR","VIOLATION"])]
annual_crime = crime_cat.groupby(["year","law_cat_cd"]).size().unstack("law_cat_cd", fill_value=0).reset_index()
annual_crime["TOTAL"] = annual_crime[["FELONY","MISDEMEANOR","VIOLATION"]].sum(axis=1)
annual_crime["YOY_CHANGE"] = annual_crime["TOTAL"].pct_change()

headers = ["Year", "Felonies", "Misdemeanors", "Violations", "TOTAL", "YoY Change"]
header_row(cs, 3, headers, [NAVY, RED, ORANGE, GREEN, DARK_BLUE, DARK_GREY])
cs.row_dimensions[3].height = 22

for i, row in annual_crime.iterrows():
    r = 4 + i
    bg = LIGHT_BG if i % 2 == 0 else WHITE
    cs.row_dimensions[r].height = 18
    vals = [int(row["year"]), row.get("FELONY",0), row.get("MISDEMEANOR",0),
            row.get("VIOLATION",0), row["TOTAL"]]
    for j, v in enumerate(vals):
        c = cs.cell(r, j+1, int(v))
        c.font = Font(name="Arial", size=10, color=DARK_GREY,
                      bold=(j == 4))
        c.fill = PatternFill("solid", fgColor=bg)
        c.alignment = Alignment(horizontal="center", vertical="center")
        if j > 0:
            c.number_format = '#,##0'
    # YoY change
    yoy = row["YOY_CHANGE"]
    yoy_c = cs.cell(r, 6, round(yoy, 4) if pd.notna(yoy) else "-")
    yoy_c.font = Font(name="Arial", size=10, color=RED if pd.notna(yoy) and yoy > 0 else GREEN)
    yoy_c.fill = PatternFill("solid", fgColor=bg)
    yoy_c.alignment = Alignment(horizontal="center")
    if pd.notna(yoy):
        yoy_c.number_format = '+0.0%;-0.0%;0.0%'

thin_border(cs, 3, 3 + len(annual_crime), 1, 6)

# Chart: Annual crime stacked bar
chart2 = BarChart()
chart2.type = "col"
chart2.grouping = "stacked"
chart2.title = "Transit Crime by Category: 2020–2024"
chart2.y_axis.title = "Incidents"
chart2.height = 14
chart2.width = 22

yr_ref = Reference(cs, min_col=1, min_row=4, max_row=3+len(annual_crime))
fel_ref = Reference(cs, min_col=2, min_row=3, max_row=3+len(annual_crime))
mis_ref = Reference(cs, min_col=3, min_row=3, max_row=3+len(annual_crime))
vio_ref = Reference(cs, min_col=4, min_row=3, max_row=3+len(annual_crime))
chart2.add_data(fel_ref, titles_from_data=True)
chart2.add_data(mis_ref, titles_from_data=True)
chart2.add_data(vio_ref, titles_from_data=True)
chart2.set_categories(yr_ref)
chart2.series[0].graphicalProperties.solidFill = RED
chart2.series[1].graphicalProperties.solidFill = ORANGE
chart2.series[2].graphicalProperties.solidFill = GREEN
cs.add_chart(chart2, "H3")

# Top 10 Felony Offenses table
cs.row_dimensions[12].height = 12
cs.merge_cells("A13:C13")
cs["A13"].value = "Top 10 Felony Offense Types (2020–2024)"
cs["A13"].font = Font(bold=True, size=11, color=WHITE, name="Arial")
cs["A13"].fill = PatternFill("solid", fgColor=NAVY)
cs["A13"].alignment = Alignment(horizontal="center", vertical="center")
cs.row_dimensions[13].height = 22

header_row(cs, 14, ["Offense Type", "Total Incidents", "% of Felonies"], [NAVY, RED, RED])
cs.row_dimensions[14].height = 20

felonies = crime[crime["law_cat_cd"]=="FELONY"]
top10 = felonies["ofns_desc"].value_counts().head(10)
total_felonies = len(felonies)

for i, (offense, count) in enumerate(top10.items()):
    r = 15 + i
    cs.row_dimensions[r].height = 18
    bg = LIGHT_BG if i % 2 == 0 else WHITE
    cs.cell(r, 1, offense.title()[:50])
    cs.cell(r, 2, int(count))
    cs.cell(r, 3, round(count/total_felonies, 4))
    for col in range(1, 4):
        c = cs.cell(r, col)
        c.font = Font(name="Arial", size=10, color=RED if i == 0 else DARK_GREY,
                      bold=(i == 0))
        c.fill = PatternFill("solid", fgColor=bg)
        c.alignment = Alignment(horizontal="center" if col > 1 else "left",
                                vertical="center", indent=1 if col == 1 else 0)
    cs.cell(r, 2).number_format = '#,##0'
    cs.cell(r, 3).number_format = '0.0%'

thin_border(cs, 14, 24, 1, 3)

# Crime by Borough
cs.merge_cells("E13:G13")
cs["E13"].value = "Felony Crime by Borough (2020–2024)"
cs["E13"].font = Font(bold=True, size=11, color=WHITE, name="Arial")
cs["E13"].fill = PatternFill("solid", fgColor=NAVY)
cs["E13"].alignment = Alignment(horizontal="center", vertical="center")

header_row(cs, 14, ["Borough", "Felonies", "% of Total"], [NAVY, RED, RED], start_col=5)

boro_crime = (felonies[felonies["boro_nm"].notna() & (felonies["boro_nm"] != "NAN")]
              .groupby("boro_nm").size().sort_values(ascending=False))
for i, (boro, count) in enumerate(boro_crime.items()):
    r = 15 + i
    bg = LIGHT_BG if i % 2 == 0 else WHITE
    cs.cell(r, 5, boro.title())
    cs.cell(r, 6, int(count))
    cs.cell(r, 7, round(count/len(felonies), 4))
    for col in range(5, 8):
        c = cs.cell(r, col)
        c.font = Font(name="Arial", size=10, color=DARK_GREY)
        c.fill = PatternFill("solid", fgColor=bg)
        c.alignment = Alignment(horizontal="center" if col > 5 else "left",
                                vertical="center", indent=1 if col == 5 else 0)
    cs.cell(r, 6).number_format = '#,##0'
    cs.cell(r, 7).number_format = '0.0%'

thin_border(cs, 14, 14 + len(boro_crime), 5, 7)

# Conditional formatting on felony column
from openpyxl.formatting.rule import ColorScaleRule
cs.conditional_formatting.add(
    f"B4:B{3+len(annual_crime)}",
    ColorScaleRule(start_type="min", start_color="FFFFFF",
                   end_type="max",   end_color=RED)
)

set_col_widths(cs, {"A": 30, "B": 14, "C": 14, "D": 14, "E": 20,
                    "F": 14, "G": 14, "H": 14})

# ══════════════════════════════════════════════════════════════════════════════
# SHEET 4 — ELEVATORS
# ══════════════════════════════════════════════════════════════════════════════
es = wb.create_sheet("🔧 Elevators")
es.sheet_view.showGridLines = False

es.merge_cells("A1:F1")
es["A1"].value = "MTA Subway Elevator & Escalator Safety: 2020 – 2025"
es["A1"].font = Font(bold=True, size=14, color=WHITE, name="Arial")
es["A1"].fill = PatternFill("solid", fgColor=ORANGE)
es["A1"].alignment = Alignment(horizontal="center", vertical="center")
es.row_dimensions[1].height = 30

# Annual summary
annual_elev = elev.groupby("year").agg(
    unscheduled=(unsch_col, "sum"),
    entrapments=(entrap_col, "sum"),
    total_outages=("total_outages", "sum") if "total_outages" in elev.columns else (unsch_col, "sum")
).reset_index()
annual_elev["entrap_yoy"] = annual_elev["entrapments"].pct_change()

headers = ["Year", "Unscheduled Outages", "Entrapments", "Entrap. YoY Change"]
header_row(es, 3, headers, [NAVY, ORANGE, RED, DARK_GREY])
es.row_dimensions[3].height = 22

for i, row in annual_elev.iterrows():
    r = 4 + i
    bg = LIGHT_BG if i % 2 == 0 else WHITE
    es.row_dimensions[r].height = 18
    es.cell(r, 1, int(row["year"]))
    es.cell(r, 2, int(row["unscheduled"]))
    es.cell(r, 3, int(row["entrapments"]))
    yoy = row["entrap_yoy"]
    es.cell(r, 4, round(yoy, 4) if pd.notna(yoy) else "-")
    for col in range(1, 5):
        c = es.cell(r, col)
        c.font = Font(name="Arial", size=10, color=DARK_GREY)
        c.fill = PatternFill("solid", fgColor=bg)
        c.alignment = Alignment(horizontal="center", vertical="center")
    es.cell(r, 2).number_format = '#,##0'
    es.cell(r, 3).number_format = '#,##0'
    if pd.notna(yoy):
        es.cell(r, 4).number_format = '+0.0%;-0.0%;0.0%'
        es.cell(r, 4).font = Font(name="Arial", size=10,
                                   color=RED if yoy > 0 else GREEN)

thin_border(es, 3, 3+len(annual_elev), 1, 4)

# Chart: entrapments
chart3 = BarChart()
chart3.type = "col"
chart3.title = "Elevator Entrapments per Year"
chart3.y_axis.title = "Entrapments"
chart3.height = 14
chart3.width = 22
yr_ref2 = Reference(es, min_col=1, min_row=4, max_row=3+len(annual_elev))
ent_ref  = Reference(es, min_col=3, min_row=3, max_row=3+len(annual_elev))
chart3.add_data(ent_ref, titles_from_data=True)
chart3.set_categories(yr_ref2)
chart3.series[0].graphicalProperties.solidFill = RED
es.add_chart(chart3, "F3")

# Worst stations
es.row_dimensions[13].height = 12
es.merge_cells("A14:C14")
es["A14"].value = "Top 10 Stations by Unscheduled Outages (2020–2025)"
es["A14"].font = Font(bold=True, size=11, color=WHITE, name="Arial")
es["A14"].fill = PatternFill("solid", fgColor=NAVY)
es["A14"].alignment = Alignment(horizontal="center", vertical="center")
es.row_dimensions[14].height = 22

if "station_name" in elev.columns:
    header_row(es, 15, ["Station Name", "Unscheduled Outages", "Entrapments"], [NAVY, ORANGE, RED])
    worst = (elev.groupby("station_name")
             .agg(out=(unsch_col, "sum"), ent=(entrap_col, "sum"))
             .sort_values("out", ascending=False).head(10))
    for i, (station, row) in enumerate(worst.iterrows()):
        r = 16 + i
        bg = LIGHT_BG if i % 2 == 0 else WHITE
        es.cell(r, 1, station.title()[:40])
        es.cell(r, 2, int(row["out"]))
        es.cell(r, 3, int(row["ent"]))
        for col in range(1, 4):
            c = es.cell(r, col)
            c.font = Font(name="Arial", size=10, color=DARK_GREY,
                          bold=(i == 0))
            c.fill = PatternFill("solid", fgColor=bg)
            c.alignment = Alignment(horizontal="center" if col > 1 else "left",
                                    vertical="center", indent=1 if col == 1 else 0)
        es.cell(r, 2).number_format = '#,##0'
        es.cell(r, 3).number_format = '#,##0'
    thin_border(es, 15, 25, 1, 3)

# Elevator vs Escalator comparison
es.merge_cells("E14:G14")
es["E14"].value = "Elevator vs Escalator: Unscheduled Outages by Year"
es["E14"].font = Font(bold=True, size=11, color=WHITE, name="Arial")
es["E14"].fill = PatternFill("solid", fgColor=NAVY)
es["E14"].alignment = Alignment(horizontal="center", vertical="center")

header_row(es, 15, ["Year", "Elevator Outages", "Escalator Outages"], [NAVY, ORANGE, DARK_BLUE], start_col=5)
equip_annual = elev.groupby(["year", equip_col])[unsch_col].sum().unstack(equip_col, fill_value=0).reset_index()
for i, row in equip_annual.iterrows():
    r = 16 + i
    bg = LIGHT_BG if i % 2 == 0 else WHITE
    es.cell(r, 5, int(row["year"]))
    elev_val = int(row.get("Elevator", row.get("ELEVATOR", 0)))
    esc_val  = int(row.get("Escalator", row.get("ESCALATOR", 0)))
    es.cell(r, 6, elev_val)
    es.cell(r, 7, esc_val)
    for col in range(5, 8):
        c = es.cell(r, col)
        c.font = Font(name="Arial", size=10, color=DARK_GREY)
        c.fill = PatternFill("solid", fgColor=bg)
        c.alignment = Alignment(horizontal="center", vertical="center")
        if col > 5:
            c.number_format = '#,##0'
thin_border(es, 15, 15+len(equip_annual), 5, 7)

set_col_widths(es, {"A": 28, "B": 20, "C": 16, "D": 16, "E": 14, "F": 18, "G": 18})

# ══════════════════════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════════════════════
wb.save(OUT)
print(f"✅ Excel workbook saved: {OUT}")
print(f"   Sheets: {wb.sheetnames}")
