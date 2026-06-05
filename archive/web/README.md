# Archived dashboard variants

Alternate Plotly Dash entry points and map backends. Superseded by the canonical pair:

- [web/DashPlay_pages.py](../../web/DashPlay_pages.py) — dashboard entry
- [web/Dash_Mapper_Leaflet.py](../../web/Dash_Mapper_Leaflet.py) — live/historic map

These files are **not** part of CI or normal operations:

- `DashPlay_discrete_pages.py` — alternate page layout using `Dash_Mapper.py`
- `Dash_Mapper.py` — earlier map implementation
- `Dash_Mapper_FSM.py` — standalone FSM map (logic now in `Dash_Mapper_Leaflet.py`)
