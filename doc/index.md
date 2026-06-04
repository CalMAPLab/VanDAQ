# VanDAQ documentation

All operator and integrator documentation for this repository lives under `doc/`. Start here, then follow the links for your task.

## Getting started


| Document                                   | Description                                           |
| ------------------------------------------ | ----------------------------------------------------- |
| [Overview](overview.md)                    | Architecture, theory of operation, and core processes |
| [Installation](operations/installation.md) | First-time setup: database, processes, verification   |


## Operations


| Document                                                                     | Description                                            |
| ---------------------------------------------------------------------------- | ------------------------------------------------------ |
| [Network configuration](operations/network_configuration.md)                 | Remote vs central servers, submission transfer         |
| [Operation and troubleshooting](operations/operation_and_troubleshooting.md) | Day-to-day commands, logs, Apache reload, common fixes |


## Guides


| Document                                              | Description                                                     |
| ----------------------------------------------------- | --------------------------------------------------------------- |
| [Adding a new instrument](adding_a_new_instrument.md) | YAML, acquirer startup, database check, dashboard wiring        |
| [Offline map tiles](guides/map_tiles.md)              | Build and serve NorCal MBTiles for the Dash map (Docker on van) |
| [Filers and export](guides/filers_and_export.md)      | Export database data to analysis files *(in progress)*          |


## Reference


| Document                                                | Description                                                    |
| ------------------------------------------------------- | -------------------------------------------------------------- |
| [Data chain configuration](data_chain_configuration.md) | YAML keys for acquirer, collector, submitter, dashboard, admin |
| [Database schema](reference/database_schema.md)         | Tables, dimensions, submission files *(in progress)*           |


## Development


| Document                                      | Description                                 |
| --------------------------------------------- | ------------------------------------------- |
| [Testing](development/testing.md)             | pytest, markers, CI                         |


## Repository entry points

- [README](../README.md) — project summary and short test setup
- [CONTRIBUTORS](../CONTRIBUTORS.md) — acknowledgements
- Example YAML: `acquirer/config/`, `collector/`, `web/DashPlay.yaml`, `vandaq_admin.yaml`
- Database dump: `schema/vandaq_schema_dump.sql`

