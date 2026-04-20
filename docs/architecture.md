# Architecture Note

## Decision

The first version uses the official Gyeonggi Data Dream Open API plus Streamlit cache, not a database.

## Why

- The source data is monthly public data, not high-frequency transactional data.
- Analysis is read-heavy and can be recomputed from the official source.
- A single-user or small-team Streamlit dashboard does not need database operations yet.
- Keeping two official source paths avoids manual upload drift while keeping the dashboard focused.

## Current Flow

1. The app calls two official Gyeonggi Data Dream Open APIs with `APP_KEY`.
2. `src.data` fetches all pages at the API maximum page size of 1,000 rows.
3. Sales data is normalized into month, region code, industry, and sales amount.
4. Publication/use data is normalized into month, city, new member count, charge amount, and use amount.
5. Streamlit `cache_data` keeps normalized frames in memory for 6 hours.
6. The dashboard aggregates by month, region, industry, and city.

## Active APIs

- `TB25BPTGGCARDCATMSALEM`: card industry middle-category local currency sales
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
