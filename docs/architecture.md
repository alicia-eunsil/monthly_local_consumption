# Architecture Note

## Decision

The first version uses the official Gyeonggi Data Dream Open API plus Streamlit cache, not a database.

## Why

- The source data is monthly public data, not high-frequency transactional data.
- Analysis is read-heavy and can be recomputed from the official source.
- A single-user or small-team Streamlit dashboard does not need database operations yet.
- Keeping one official source path avoids manual upload drift.

## Current Flow

1. The app calls the official Gyeonggi Data Dream Open API with `APP_KEY`.
2. `src.data` fetches all pages at the API maximum page size of 1,000 rows.
3. Columns are normalized into a standard schema.
4. Streamlit `cache_data` keeps the normalized frame in memory for 6 hours.
5. The dashboard aggregates by month, region, and industry.

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
