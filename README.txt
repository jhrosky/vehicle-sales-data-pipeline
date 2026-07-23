This is a quick demo project showing my approach to data ingestion, validation,
and dbt modeling — built to demonstrate how I structure a pipeline from raw data
through staging, intermediate, and mart layers, including data quality checks and
rejection handling along the way.

J. Rosky — Vehicle Sales Data Pipeline
==========================================
Submission contains:
- python/ : ingestion script + CSV outputs
- dbt/    : staging, intermediate, mart models + schema.yml
- Observability_Resilience.txt : Part 5 write-up
- load_strategy_outline.txt : Part 3 load strategy

Script output below confirms successful execution in Colab:
==========================================


── Part 1: Ingest & Normalize ──
  Raw vehicles: 12 records
  Raw sales:    5 records
  Dealerships:  4 records

  Dedup: 12 → 10 vehicles (2 duplicates removed)

── Part 2: Validation & Data Quality ──

  Vehicles — clean: 8, rejected: 2
    vehicle_id 202: invalid mileage: -10.0 (must be >= 0); invalid date_listed: 2205-01-01 00:00:00 (must not be in the future)
    vehicle_id 211: invalid year: 2030 (must be 1886–2026); invalid VIN: '' (must be exactly 17 characters)

  Sales — clean: 3, rejected: 2
    sale_id 3: vehicle_id 202 not in valid vehicles (orphaned sale — source vehicle was rejected)
    sale_id 6: vehicle_id 211 not in valid vehicles (orphaned sale — source vehicle was rejected)

── Part 3: Writing Outputs ──

Outputs written to /content/output/

  Clean vehicles:
 vehicle_id      make    model  year               VIN  mileage  dealership_id date_listed
        101     Honda    Civic  1999 JHMEJ8548XS437822 120000.0             13  2025-10-01
        210     Honda  Crf450X  2005 JH2PE06285K000596      0.0             10  2025-09-01
        102     Dodge Ram 2500  2024 3B6KF26692M894437  56998.0             11  2025-01-01
        103    Toyota   Tundra  2018 5TFEM5F17JX131717 120000.0             11  2025-01-01
        104 Chevrolet    South  2018 1GB2KUEY2JZ129805 845654.0             12  2025-01-01
        201 Chevrolet    Cruze  1999 1G1PB5SH4D7216979  15422.0             12  2025-01-01
        212     Volvo Aero Wia  2000 4VGWDAJF1VN741198   5400.0             12  2025-01-01
        203       Gmc    P3500  1985 1GTKP32M2F3953368 999999.0             13  2024-01-01

  Rejected vehicles:
 vehicle_id   make  model  year               VIN  mileage date_listed                                                                                                      _error
        202 Toyota Pickup  1987 JT4RN67S4H0547559    -10.0  2205-01-01 invalid mileage: -10.0 (must be >= 0); invalid date_listed: 2205-01-01 00:00:00 (must not be in the future)
        211 Toyota   Rav4  2030                   999999.0  2025-01-01                     invalid year: 2030 (must be 1886–2026); invalid VIN: '' (must be exactly 17 characters)

  Clean sales:
 sale_id  vehicle_id   price  total_sale  date_sold
       1         101 12399.0     12399.0 2025-11-15
       2         203 15000.0     11000.0 2025-11-15
       5         102 25603.0     25542.0 2025-11-15

  Rejected sales:
 sale_id  vehicle_id   price  total_sale                                                                             _error
       3         202 4525.12     5300.09 vehicle_id 202 not in valid vehicles (orphaned sale — source vehicle was rejected)
       6         211 1000.00     1000.00 vehicle_id 211 not in valid vehicles (orphaned sale — source vehicle was rejected)

=======================================================
  Done! Download files from /content/output/
=======================================================
