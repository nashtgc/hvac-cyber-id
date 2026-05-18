# Data

## v1 (this version)

Synthetic only. Each lookup returns a uniformly sampled MW value within a BA-specific range that approximates published hourly demand averages from EIA Open Data (US BAs) and AESO/IESO dashboards (Canadian ISOs). Generation lives in `grid_load_agent/app/agent.py` (`_MW_RANGES` table + `_mock_load`).

The data is intentionally not realistic enough to be misleading. Every response carries a "(mock)" disclosure, and the system prompt forces the agent to preserve it.

### Supported BAs and approximate load ranges (MW)

| BA      | Operator                                          | Range (MW)       |
|---------|---------------------------------------------------|------------------|
| PJM     | PJM Interconnection (13 US states + DC)           | 65,000–145,000   |
| MISO    | Midcontinent ISO (15 US states + Manitoba)        | 65,000–130,000   |
| ERCOT   | Electric Reliability Council of Texas             | 35,000–85,000    |
| CAISO   | California ISO                                    | 22,000–50,000    |
| SPP     | Southwest Power Pool                              | 25,000–55,000    |
| NYISO   | New York ISO                                      | 16,000–32,000    |
| ISO-NE  | ISO New England                                   | 12,000–26,000    |
| AESO    | Alberta Electric System Operator (Canada)         | 9,500–12,500     |
| IESO    | Ontario Independent Electricity System Operator   | 12,000–25,000    |

## v2 (roadmap)

Primary live feeds:

- **EIA Open Data** (US RTO/ISO): https://www.eia.gov/opendata/, public, free, API key, hourly demand by Balancing Authority. Endpoint: `electricity/rto/region-data`.
- **AESO** (Alberta, Canada): public Real-Time Reports via http://ets.aeso.ca/.
- **IESO** (Ontario, Canada): public hourly demand at https://www.ieso.ca/Power-Data.

Optional secondary feed for cross-region comparison:

- **ENTSO-E Transparency Platform** (EU): https://transparency.entsoe.eu/, public, free, OAuth-token, `ActualTotalLoad` (A65) endpoint. Not part of v2 critical-path; would land in v3 if multi-region framing matters.
