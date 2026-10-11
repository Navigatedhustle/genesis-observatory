# Architecture

Vanilla browser UI → FastAPI → SQLite WAL store and a seeded 48×48 world. Organisms inherit compact neural controllers. Separate investigator, contact and steward brokers restrict model tools and record observations. Local Ollama serves language models.

## Implemented endpoints inspected from source

| Method | Route | Source |
| --- | --- | --- |
| GET | `/` | `genesis/app.py` |
| GET | `/api/state` | `genesis/app.py` |
| POST | `/api/control` | `genesis/app.py` |
| POST | `/api/checkpoint` | `genesis/app.py` |
| POST | `/api/branch` | `genesis/app.py` |
| POST | `/api/restore` | `genesis/app.py` |
| POST | `/api/intervention` | `genesis/app.py` |
| GET | `/api/replay/{world}` | `genesis/app.py` |
| GET | `/api/export` | `genesis/app.py` |
| POST | `/api/chat` | `genesis/app.py` |
| POST | `/api/evaluate` | `genesis/app.py` |
| POST | `/api/jobs/{job}/cancel` | `genesis/app.py` |
| POST | `/api/arrival` | `genesis/app.py` |
| POST | `/api/communicate` | `genesis/app.py` |
| POST | `/api/first-contact` | `genesis/app.py` |
| GET | `/api/entity/{world}/{entity}` | `genesis/app.py` |
| POST | `/api/agents/{world}/{actor}/configure` | `genesis/app.py` |
| POST | `/api/god/control` | `genesis/app.py` |
| POST | `/api/god/chat` | `genesis/app.py` |
| POST | `/api/god/act` | `genesis/app.py` |
| GET | `/api/god/state` | `genesis/app.py` |
| GET | `/api/god/jobs/{job}` | `genesis/app.py` |
| POST | `/api/god/jobs/{job}/cancel` | `genesis/app.py` |
| GET | `/api/god/export/{world}` | `genesis/app.py` |

These routes establish implementation shape. They do not establish successful provider integration or model quality. Generated state and data stores are excluded from the repository.
