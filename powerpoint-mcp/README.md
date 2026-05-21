# aspose-pptx

REST wrapper around Aspose.Slides for Python via .NET. Lives here so the
moltchat native-export sandbox (`backend/exports/native/`) can drive
per-element PPTX construction over HTTP from a Mac — Aspose.Slides
requires the .NET runtime, so this service runs in Docker on Render.

Forked down from `stash_desktop/powerpoint-mcp`; the MCP/agent-editing
surface was stripped and replaced with a thin FastAPI layer matching the
sandbox's `SlideSpec` schema.

## Endpoints

```
GET    /healthz                                       → {"ok": true}
POST   /sessions                                      → {session_id}
DELETE /sessions/{sid}
POST   /sessions/{sid}/slides                         → {slide_index}
POST   /sessions/{sid}/slides/{idx}/text              → {shape_index}
POST   /sessions/{sid}/slides/{idx}/image             → {shape_index}
POST   /sessions/{sid}/slides/{idx}/raster            → {shape_index}
POST   /sessions/{sid}/slides/{idx}/table             → {shape_index}
GET    /sessions/{sid}/pptx                           → PPTX bytes
```

Request schemas: see `src/models.py`. Body field names match
`backend/exports/native/spec.py` so the sandbox can `asdict(spec)` and
POST it.

## Auth

If `ASPOSE_PPTX_TOKEN` is set, every non-`/healthz` request must carry
`Authorization: Bearer <token>`. Unset → open access (local dev).

## Env vars

| Var | Purpose |
|---|---|
| `ASPOSE_LICENSE_DATA` | base64-encoded `.lic` file. Unset → 30-day trial mode. |
| `ASPOSE_PPTX_TOKEN`   | shared bearer token. Unset → no auth. |
| `MAX_SESSIONS`        | concurrent sessions before LRU eviction (default 3). |
| `SESSION_TIMEOUT_MINUTES` | idle TTL (default 30). |
| `PORT`                | bind port (Render injects). |

## Why not run locally on macOS

Aspose.Slides for Python uses `pythonnet` against .NET, which only ships
binaries for Linux/Windows. Local iteration: deploy to Render and point
`ASPOSE_PPTX_URL` at the public URL.
