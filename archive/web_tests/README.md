# Archived web manual test scripts

These files were moved from `web/tests/` in favor of the pytest suite under `tests/`.

They are **not** part of CI and are kept for reference only:

- `query_test.py` — timing script against a live Postgres database
- `vandaq_measurements_query.py` — older copy of query helpers (see `common/vandaq_measurements_query.py`)
- `vandaq_schema.py` — older copy of schema models (see `common/vandaq_schema.py`)

Do not run these against production databases without reviewing hardcoded connection strings.
