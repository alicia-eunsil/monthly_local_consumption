# Architecture Note

## Decision

The current version uses the official Gyeonggi Data Dream Open API plus session cache, not a database.

## Why

- The source data is monthly public data, not high-frequency transactional data.
- Analysis is read-heavy and can be recomputed from the official source.
- A single-user or small-team Streamlit dashboard does not need database operations yet.
- Keeping one official source path avoids manual upload drift while keeping the dashboard focused.

## Current Flow

1. The app calls the official Gyeonggi Data Dream Open API with `APP_KEY`.
2. `src.data` fetches all pages at the API maximum page size of 1,000 rows.
3. Large paginated APIs are fetched concurrently with per-page retries.
4. Publication/use data is normalized into month, city, new member count, charge amount, and use amount.
5. Streamlit session state keeps normalized frames in memory for the active user session.
6. The dashboard aggregates by month and city.

## Active APIs

- `RegionMnyPublctUse`: local currency publication and use status

## When To Add A Database

Add SQLite, DuckDB, or Postgres if one of these becomes true:

- Multiple large source files need to be joined repeatedly.
- Historical snapshots must be archived with load timestamps.
- The dashboard needs fast keyword search across millions of rows.
- Multiple users need write access, annotations, or saved views.
- Data updates become scheduled and automated.

## Likely Next Step

If API loading becomes slow, add a Parquet cache before adding a database.

Recommended order:

1. Open API + Streamlit cache
2. Open API + Parquet cache
3. DuckDB over Parquet
4. Postgres only if multi-user persistence is needed
