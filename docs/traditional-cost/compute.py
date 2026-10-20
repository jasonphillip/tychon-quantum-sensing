#!/usr/bin/env python3
"""Traditional build cost for the scope in this repository. Every number on the page comes from here.

Pay: Bureau of Labor Statistics, Occupational Employment and Wage Statistics, May 2025, national
median hourly wage by occupation (bls.gov/news.release/ocwage.t01.htm). Benefits: 30.0 percent of
private-industry employer cost in June 2026 (bls.gov/news.release/ecec.nr0.htm), so employer cost is
wages divided by 0.70. A working year is 2,080 hours. The plan is five people for nine months.
"""
import sys
HOURS_YEAR = 2080
BENEFIT_SHARE = 0.30
MONTHS = 9
TEAM = [  # role, BLS occupation, median hourly USD, what they build
 ("Technical lead", "Architectural and engineering managers", 82.34,
  "Architecture, the technical plan and funding proposal, the verification system that checks every claim against evidence, the technical report."),
 ("Quantum-sensing physicist", "Physicists", 82.81,
  "The NV spectrum simulator, its fits to four public measured datasets, the dataset pipelines, the classical field estimators."),
 ("FPGA and embedded engineer", "Computer hardware engineers", 77.76,
  "The PolarFire SoC controller in HLS with its fabric clamp and watchdog, INT8 inference on the kit, the Linux runtime loop, the replay harness, the CUDA-Q fabric demonstrations."),
 ("Machine-learning engineer", "Computer and information research scientists", 67.45,
  "Scalar estimation models, INT8 and hierarchical INT8 quantisation, TFLite export, the learned vector tracker and its registered comparison study, measured-data pilots."),
 ("Software and test engineer", "Software developers", 65.38,
  "Test suites, data contracts, reproduction scripts, benchmarks, the dashboard and demo recordings, the documentation build."),
]
EQUIPMENT = [("PolarFire SoC Icicle kit", 500), ("three GPU workstations", 12000), ("FPGA build host", 1000)]

def cost(hourly, months): return hourly * HOURS_YEAR / (1 - BENEFIT_SHARE) * months / 12
def k(v): return f"${v/1000:,.0f}k"

rows = [(r, occ, h, why, cost(h, MONTHS)) for r, occ, h, why in TEAM]
labor = sum(c for *_, c in rows); equip = sum(v for _, v in EQUIPMENT); total = labor + equip
four = sum(c for *_, c in rows[:4]); year = labor * 12 / MONTHS + equip
print("| Who | Time | What they build | Pay basis | Cost |")
print("|---|---|---|---|---|")
for r, occ, h, why, c in rows:
    print(f"| {r} | {MONTHS} months | {why} | {occ}, ${h:.2f}/h | {k(c)} |")
print(f"| Equipment | | {', '.join(n for n, _ in EQUIPMENT)}. | List price | {k(equip)} |")
print(f"| **Total** | **{len(TEAM) * MONTHS} person-months** | | | **{k(total)}** |")
if "--extras" in sys.argv:
    print(f"\nlabor={labor:,.0f} equip={equip:,} total={total:,.0f} four_people_9mo={four:,.0f} five_people_12mo={year:,.0f}")
