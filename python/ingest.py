"""
Vehicle Sales Data Pipeline
====================================
Ingests vehicle, sales, and dealership data from mock API endpoints
(local JSON files that simulate paginated HTTP responses).

Covers:
  Part 1 — Ingest & Normalize
  Part 2 — Validation & Data Quality
  Part 3 — Load Strategy (CSV output + DDL)

Author: Jesse Rosky
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
API_DIR    = DATA_DIR / "mock_api"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

CURRENT_YEAR  = datetime.now().year
MIN_CAR_YEAR  = 1886        # Year of the first automobile
VIN_LENGTH    = 17
TODAY         = pd.Timestamp.now().normalize()  # Today at midnight for date comparisons


# ── Part 1: Mock HTTP Client ──────────────────────────────────────────────────

def mock_get(endpoint: str, params: dict = None) -> dict:
    """
    Simulates an HTTP GET request to a vehicle sales API.

    In a real environment this would be:
        import requests
        response = requests.get(BASE_URL + endpoint, params=params)
        return response.json()

    For this project, we read from local JSON files instead.
    The logic (pagination, params) is identical to a real HTTP client.
    """
    params = params or {}

    if endpoint == "/v1/dealerships":
        file_path = DATA_DIR / "dealerships.json"

    elif endpoint == "/v1/vehicles":
        page = params.get("page", 1)
        file_path = API_DIR / f"vehicles_page_{page}.json"

    elif endpoint == "/v1/sales":
        page = params.get("page", 1)
        file_path = API_DIR / f"sales_page_{page}.json"

    else:
        raise ValueError(f"Unknown endpoint: {endpoint}")

    # If the file doesn't exist, treat it like a 200 response with no data.
    # This is how real pagination works — the loop stops when a page is empty.
    if not file_path.exists():
        return {"data": []}

    with open(file_path, "r") as f:
        return json.load(f)


# ── Part 1: Ingest ────────────────────────────────────────────────────────────

def ingest_paginated(endpoint: str, page_size: int = 100) -> pd.DataFrame:
    """
    Fetches all pages from a paginated API endpoint.

    Keeps requesting pages until an empty response is returned —
    the same pattern you'd use against a real REST API.

    Idempotent: re-running always fetches fresh data from the source,
    so there's no risk of stale state or double-loading.
    """
    all_records = []
    page = 1

    while True:
        response = mock_get(endpoint, params={"page": page, "page_size": page_size})
        records = response.get("data", [])

        if not records:
            # Empty page means we've consumed all available data
            break

        all_records.extend(records)
        page += 1

    return pd.DataFrame(all_records)


def ingest_dealerships() -> pd.DataFrame:
    """
    Fetches the dealership dimension table.
    This endpoint is not paginated — it returns all records in one response.
    """
    response = mock_get("/v1/dealerships")
    return pd.DataFrame(response.get("data", []))


# ── Part 1: Normalize ─────────────────────────────────────────────────────────

def normalize_vehicles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardizes raw vehicle data before validation.

    - Title-cases make and model (handles HONDA → Honda, CRUZE → Cruze)
    - Casts year to integer and mileage to float for numeric comparisons
    - Parses date_listed as a proper datetime (catches malformed dates like 2205-01-01)
    - Strips whitespace from VIN
    """
    df = df.copy()
    df["make"]        = df["make"].str.strip().str.title()
    df["model"]       = df["model"].str.strip().str.title()
    df["year"]        = pd.to_numeric(df["year"], errors="coerce")
    df["mileage"]     = pd.to_numeric(df["mileage"], errors="coerce")
    df["date_listed"] = pd.to_datetime(df["date_listed"], errors="coerce")
    df["VIN"]         = df["VIN"].str.strip()
    return df


def normalize_sales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardizes raw sales data before validation.

    - Casts price and total_sale to float, which naturally handles
      trailing-decimal strings like "12399." → 12399.0
    - Rounds to 2 decimal places for currency consistency
    - Parses date_sold as a proper datetime
    """
    df = df.copy()
    df["price"]      = pd.to_numeric(df["price"],      errors="coerce").round(2)
    df["total_sale"] = pd.to_numeric(df["total_sale"], errors="coerce").round(2)
    df["date_sold"]  = pd.to_datetime(df["date_sold"], errors="coerce")
    return df


def deduplicate_vehicles(df: pd.DataFrame) -> pd.DataFrame:
    """
    Removes duplicate vehicle_id records using a deterministic survivor rule:
    keep the record with the most recent date_listed.

    Why this rule? The most recently listed record is most likely to reflect
    the current state of the vehicle (updated dealership, corrected data, etc.)

    If two records share the same date_listed, the first occurrence is kept —
    this makes the deduplication fully deterministic across re-runs.

    Duplicates found in this dataset:
      - vehicle_id 101: page 1 (2023-05-23) vs page 2 (2025-10-01) → page 2 survives
      - vehicle_id 212: page 2 (2024-01-01) vs page 3 (2025-01-01) → page 3 survives
    """
    df = df.sort_values("date_listed", ascending=False)
    df = df.drop_duplicates(subset=["vehicle_id"], keep="first")
    return df.reset_index(drop=True)


# ── Part 2: Validation ────────────────────────────────────────────────────────

def validate_vehicles(df: pd.DataFrame):
    """
    Applies schema and business rule validation to vehicle records.

    Rules:
      - year:        must be between 1886 (first automobile) and current year
      - mileage:     must be >= 0 (negative mileage is physically impossible)
      - VIN:         must be non-empty and exactly 17 characters (NHTSA standard)
      - date_listed: must be a valid date and must not be in the future

    Returns (clean_df, rejected_df).
    Rejected records include an _error column explaining why they were rejected.
    """
    error_list = []

    for _, row in df.iterrows():
        row_errors = []

        # Year check
        if pd.isna(row["year"]) or not (MIN_CAR_YEAR <= int(row["year"]) <= CURRENT_YEAR):
            row_errors.append(f"invalid year: {row['year']} (must be {MIN_CAR_YEAR}–{CURRENT_YEAR})")

        # Mileage check
        if pd.isna(row["mileage"]) or row["mileage"] < 0:
            row_errors.append(f"invalid mileage: {row['mileage']} (must be >= 0)")

        # VIN check — must be non-empty and exactly 17 characters
        vin = str(row.get("VIN", "")).strip()
        if not vin or len(vin) != VIN_LENGTH:
            row_errors.append(f"invalid VIN: '{vin}' (must be exactly {VIN_LENGTH} characters)")

        # date_listed check — must be a valid past or present date
        if pd.isna(row["date_listed"]) or row["date_listed"] > TODAY:
            row_errors.append(f"invalid date_listed: {row['date_listed']} (must be a valid date not in the future)")

        error_list.append("; ".join(row_errors) if row_errors else None)

    df = df.copy()
    df["_error"] = error_list

    clean    = df[df["_error"].isna()].drop(columns=["_error"]).reset_index(drop=True)
    rejected = df[df["_error"].notna()].reset_index(drop=True)

    return clean, rejected


def validate_sales(df: pd.DataFrame, valid_vehicle_ids: set):
    """
    Applies schema and business rule validation to sales records.

    Rules:
      - price:      must be a positive number
      - total_sale: must be a positive number
      - date_sold:  must be a valid date
      - vehicle_id: must exist in the set of clean (non-rejected) vehicles
                    — orphaned sales with no valid vehicle are rejected

    Returns (clean_df, rejected_df).
    """
    error_list = []

    for _, row in df.iterrows():
        row_errors = []

        # Price check
        if pd.isna(row["price"]) or row["price"] <= 0:
            row_errors.append(f"invalid price: {row['price']} (must be > 0)")

        # Total sale check
        if pd.isna(row["total_sale"]) or row["total_sale"] <= 0:
            row_errors.append(f"invalid total_sale: {row['total_sale']} (must be > 0)")

        # Date check
        if pd.isna(row["date_sold"]):
            row_errors.append(f"invalid date_sold: {row['date_sold']}")

        # Referential integrity — sale must link to a valid vehicle
        if row["vehicle_id"] not in valid_vehicle_ids:
            row_errors.append(
                f"vehicle_id {row['vehicle_id']} not found in valid vehicles "
                f"(orphaned sale — source vehicle was rejected)"
            )

        error_list.append("; ".join(row_errors) if row_errors else None)

    df = df.copy()
    df["_error"] = error_list

    clean    = df[df["_error"].isna()].drop(columns=["_error"]).reset_index(drop=True)
    rejected = df[df["_error"].notna()].reset_index(drop=True)

    return clean, rejected


# ── Part 3: Load Strategy ─────────────────────────────────────────────────────

def write_outputs(
    vehicles_clean,
    sales_clean,
    dealerships,
    vehicles_rejected,
    sales_rejected,
):
    """
    Writes all clean and rejected datasets to CSV in the output directory.

    CSV is the delivery format for this project.
    In production, these CSVs would be loaded to Redshift via:
      - COPY command from S3 (bulk load, most efficient for Redshift)
      - Or a tool like Fivetran, AWS Glue, or a Python script using psycopg2/SQLAlchemy

    The load would be idempotent using MERGE or staging tables +
    INSERT ... WHERE NOT EXISTS patterns.
    """
    vehicles_clean.to_csv(OUTPUT_DIR / "vehicles_clean.csv",      index=False)
    sales_clean.to_csv(OUTPUT_DIR / "sales_clean.csv",            index=False)
    dealerships.to_csv(OUTPUT_DIR / "dealerships.csv",            index=False)
    vehicles_rejected.to_csv(OUTPUT_DIR / "vehicles_rejected.csv", index=False)
    sales_rejected.to_csv(OUTPUT_DIR / "sales_rejected.csv",       index=False)
    print(f"\n  Files written to: {OUTPUT_DIR}/")
    for f in sorted(OUTPUT_DIR.iterdir()):
        print(f"    {f.name}")


# DDL statements for Redshift/Snowflake warehouse load
# These would be run once to create the target tables before loading.
WAREHOUSE_DDL = """
-- ================================================================
-- Vehicle Sales Warehouse DDL
-- Compatible with: Amazon Redshift / Snowflake (ANSI SQL)
-- Run once to create target tables before loading CSV data
-- ================================================================

-- Dealership dimension table (loaded first — referenced by vehicles)
CREATE TABLE IF NOT EXISTS staging.dealerships (
    dealership_id   INTEGER         NOT NULL,
    name            VARCHAR(255)    NOT NULL,
    region          VARCHAR(100),
    PRIMARY KEY (dealership_id)
);

-- Vehicle table (loaded second — referenced by sales)
CREATE TABLE IF NOT EXISTS staging.vehicles (
    vehicle_id      INTEGER         NOT NULL,
    make            VARCHAR(100)    NOT NULL,
    model           VARCHAR(100)    NOT NULL,
    year            INTEGER         NOT NULL    CHECK (year BETWEEN 1886 AND 2100),
    vin             VARCHAR(17)     NOT NULL,
    mileage         NUMERIC(10, 1)  NOT NULL    CHECK (mileage >= 0),
    dealership_id   INTEGER                     REFERENCES staging.dealerships(dealership_id),
    date_listed     DATE            NOT NULL,
    PRIMARY KEY (vehicle_id),
    UNIQUE (vin)
);

-- Sales fact table (loaded last — depends on vehicles)
CREATE TABLE IF NOT EXISTS staging.sales (
    sale_id         INTEGER         NOT NULL,
    vehicle_id      INTEGER         NOT NULL    REFERENCES staging.vehicles(vehicle_id),
    price           NUMERIC(12, 2)  NOT NULL    CHECK (price > 0),
    total_sale      NUMERIC(12, 2)  NOT NULL    CHECK (total_sale > 0),
    date_sold       DATE            NOT NULL,
    PRIMARY KEY (sale_id)
);

-- ================================================================
-- Redshift-specific load commands (run after tables are created)
-- Replace <bucket> and <iam_role> with your actual values
-- ================================================================

-- COPY staging.dealerships
-- FROM 's3://<bucket>/output/dealerships.csv'
-- IAM_ROLE '<iam_role>'
-- CSV IGNOREHEADER 1;

-- COPY staging.vehicles
-- FROM 's3://<bucket>/output/vehicles_clean.csv'
-- IAM_ROLE '<iam_role>'
-- CSV IGNOREHEADER 1;

-- COPY staging.sales
-- FROM 's3://<bucket>/output/sales_clean.csv'
-- IAM_ROLE '<iam_role>'
-- CSV IGNOREHEADER 1;
"""


# ── Main Entrypoint ───────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Vehicle Sales Data Pipeline")
    print("=" * 55)

    # ── Part 1: Ingest & Normalize ────────────────────────────────────────────
    print("\n── Part 1: Ingest & Normalize ──")

    raw_vehicles  = ingest_paginated("/v1/vehicles")
    raw_sales     = ingest_paginated("/v1/sales")
    dealerships   = ingest_dealerships()

    print(f"  Raw vehicles ingested:  {len(raw_vehicles)} records (across all pages)")
    print(f"  Raw sales ingested:     {len(raw_sales)} records (across all pages)")
    print(f"  Dealerships ingested:   {len(dealerships)} records")

    # Normalize: clean up types, casing, and date formats
    raw_vehicles = normalize_vehicles(raw_vehicles)
    raw_sales    = normalize_sales(raw_sales)

    # Deduplicate: one record per vehicle_id, most recent date_listed survives
    pre_dedup_count = len(raw_vehicles)
    raw_vehicles = deduplicate_vehicles(raw_vehicles)
    print(f"\n  Deduplication: {pre_dedup_count} → {len(raw_vehicles)} vehicles")
    print(f"  (Removed {pre_dedup_count - len(raw_vehicles)} duplicate vehicle_id records)")

    # ── Part 2: Validate ──────────────────────────────────────────────────────
    print("\n── Part 2: Validation & Data Quality ──")

    vehicles_clean, vehicles_rejected = validate_vehicles(raw_vehicles)

    # Pass only valid vehicle IDs into sales validation
    # so orphaned sales (referencing rejected vehicles) are caught
    valid_vehicle_ids = set(vehicles_clean["vehicle_id"].tolist())
    sales_clean, sales_rejected = validate_sales(raw_sales, valid_vehicle_ids)

    print(f"\n  Vehicles:")
    print(f"    Clean:    {len(vehicles_clean)}")
    print(f"    Rejected: {len(vehicles_rejected)}")

    if not vehicles_rejected.empty:
        print("\n  Vehicle rejection details:")
        for _, row in vehicles_rejected.iterrows():
            print(f"    vehicle_id {int(row['vehicle_id'])}: {row['_error']}")

    print(f"\n  Sales:")
    print(f"    Clean:    {len(sales_clean)}")
    print(f"    Rejected: {len(sales_rejected)}")

    if not sales_rejected.empty:
        print("\n  Sales rejection details:")
        for _, row in sales_rejected.iterrows():
            print(f"    sale_id {int(row['sale_id'])}: {row['_error']}")

    # ── Part 3: Write Outputs ─────────────────────────────────────────────────
    print("\n── Part 3: Load Strategy ──")
    print("\n  Writing CSV outputs...")
    write_outputs(
        vehicles_clean,
        sales_clean,
        dealerships,
        vehicles_rejected,
        sales_rejected,
    )

    print("\n  Warehouse DDL (create tables before loading):")
    print(WAREHOUSE_DDL)

    print("\n" + "=" * 55)
    print("  Pipeline complete.")
    print("=" * 55)


if __name__ == "__main__":
    main()
