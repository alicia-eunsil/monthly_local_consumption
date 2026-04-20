# Architecture Note

## Decision

The first version uses file-backed data plus Streamlit cache, not a database.

## Why

- The source data is monthly public data, not high-frequency transactional data.
- Analysis is read-heavy and can be recomputed from source CSV files.
- A single-user or small-team Streamlit dashboard does not need database operations yet.
- Keeping raw CSV files in `data/` makes the pipeline transparent and easy to replace.

## Current Flow

1. User uploads a CSV or selects a CSV from `data/`.
2. `src.data` reads the file with Korean encoding fallbacks.
3. Columns are normalized into a standard schema.
4. Streamlit `cache_data` keeps the normalized frame in memory.
5. The dashboard aggregates by month, region, and industry.

## When To Add A Database

Add SQLite, DuckDB, or Postgres if one of these becomes true:

- Multiple large source files need to be joined repeatedly.
- Historical snapshots must be archived with load timestamps.
- The dashboard needs fast keyword search across millions of rows.
- Multiple users need write access, annotations, or saved views.
- Data updates become scheduled and automated.

## Likely Next Step

If CSV loading becomes slow, add a Parquet cache before adding a database.

Recommended order:

1. CSV + Streamlit cache
2. CSV + Parquet cache
3. DuckDB over Parquet
4. Postgres only if multi-user persistence is needed
