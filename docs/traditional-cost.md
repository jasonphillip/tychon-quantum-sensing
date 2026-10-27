# What this would traditionally cost to build

I estimate five specialists over about nine months to build this repository by traditional staffing, roughly $850,000 in pay, benefits and equipment at United States median rates. The table names each role, its work, and the cost basis. The repository records kit measurements and the agent-directed build in the [case study](case-study.md).

## The team

| Who | Time | What they build | Pay basis | Cost |
|---|---|---|---|---|
| Technical lead | 9 months | Architecture, the technical plan and funding proposal, the verification system that checks every claim against evidence, the technical report. | Architectural and engineering managers, $82.34/h | $184k |
| Quantum-sensing physicist | 9 months | The NV spectrum simulator, its fits to four public measured datasets, the dataset pipelines, the classical field estimators. | Physicists, $82.81/h | $185k |
| FPGA and embedded engineer | 9 months | The PolarFire SoC controller in HLS with its fabric clamp and watchdog, INT8 inference on the kit, the Linux runtime loop, the replay harness, the CUDA-Q fabric demonstrations. | Computer hardware engineers, $77.76/h | $173k |
| Machine-learning engineer | 9 months | Scalar estimation models, INT8 and hierarchical INT8 quantisation, TFLite export, the learned vector tracker and its registered comparison study, measured-data pilots. | Computer and information research scientists, $67.45/h | $150k |
| Software and test engineer | 9 months | Test suites, data contracts, reproduction scripts, benchmarks, the dashboard and demo recordings, the documentation build. | Software developers, $65.38/h | $146k |
| Equipment | | PolarFire SoC Icicle kit, three GPU workstations, FPGA build host. | List price | $14k |
| **Total** | **45 person-months** | | | **$851k** |

Each cost is that occupation's median hourly wage (Bureau of Labor Statistics, May 2025) times 2,080 hours a year, divided by 0.70 because benefits are 30 percent of private-industry employer cost (Bureau of Labor Statistics, June 2026), for nine months. With four people the total comes to about $690,000, and a full year for all five comes to about $1.1 million.

## How this repository was actually built

One person built it, directing AI coding agents over 113 working days between July 2025 and October 2026, in 217 recorded build sessions ([count method](workflow-retrospective.md#activity-count-methodology)). The technical plan called for a team of four. A verification workbench checked each claim against its evidence before it stayed in, which is the job a review team would otherwise do.

## Reproduce the numbers

`python3 docs/traditional-cost/compute.py` prints the table from the wage rows and assumptions in the script.

## Sources

- Bureau of Labor Statistics, Occupational Employment and Wage Statistics, May 2025, Table 1: https://www.bls.gov/news.release/ocwage.t01.htm
- Bureau of Labor Statistics, Employer Costs for Employee Compensation, June 2026: https://www.bls.gov/news.release/ecec.nr0.htm

Both read on 2026-10-20.

