# komoot-mcp

MCP server for [Komoot](https://www.komoot.com/) — the most comprehensive Komoot API wrapper available. Tours, highlights, route planning, exports, and more.

Built with Python + [FastMCP](https://github.com/jlowin/fastmcp). Combines capabilities from [kompy](https://github.com/Tsadoq/kompy), [KomootGPX](https://github.com/timschneeb/KomootGPX), [komPYoot](https://pypi.org/project/komPYoot/), [export-komoot](https://github.com/pieterclaerhout/export-komoot), [Eric-AI-M/komoot-mcp-server](https://github.com/Eric-AI-M/komoot-mcp-server) and [Filip-Kin/komoot-mcp](https://github.com/Filip-Kin/komoot-mcp) into a single MCP server.

## Features

### Tours
- **List tours** — filter by type (planned/recorded), sport, visibility, name, date range, with sorting and pagination
- **Get tour detail** — distance, elevation, duration, sport, difficulty, surfaces (also via share token)
- **Get full tour** — metadata, surfaces, way types, directions, participants, timeline highlights and photos in one call
- **Update tour** — name, sport, visibility, description
- **Delete tour**

### Exports
- **Download GPX** — full GPS trace, inline or saved to a file
- **Download FIT** — Garmin/ANT+ format (planned tours only), saved to a file
- **Export all tours** — bulk backup to a folder, skipping files already present

### Upload
- **Upload tour** — GPX text, or a local `.gpx` / `.fit` / `.tcx` file; sets sport, name and visibility; flags duplicates

### Route planning & geocoding
- **Plan route** — Komoot route planner between waypoints (fitness level, round trip)
- **Plan and save tour** — plan and save as a planned tour in one call (no GPX round-trip through the chat)
- **Import GPX route** / **Create planned tour** — match an external GPX on Komoot's network and save it
- **Tour line** — lightweight simplified geometry
- **Geocode / reverse geocode** — place name ↔ coordinates via Komoot's Photon service

### Discovery
- **Find Smart Tours** — Komoot's suggested routes around a point, filterable by route attributes (forests, lakes, mountain huts…) or by a highlight they pass through
- **List route attributes** — attributes available around a point
- **Smart Tour detail / GPX**
- **Discover near** — editorial collections around a point
- **Collections** — collection metadata and its tours

### Highlights
- **Get highlight** — community points of interest, optionally with tips and recommenders
- **Highlight tips / photos** — paginated
- **Highlights nearby** — community highlights within a radius, filterable by sport
- **User highlights** — highlights recommended by a user
- **Bookmarks** — list, add and remove saved highlights
- **Tour images** — photos attached to a tour

### Sharing
- **Create / revoke share link** for a tour
- **Read shared tour** from a Komoot URL (with or without share token)

### Streams
- **Coordinates** — lat, lng, altitude, timestamp sequence
- **Surfaces** — surface types per segment (asphalt, gravel, dirt...)
- **Way types** — road, bike path, trail, etc.
- **Directions** — turn-by-turn navigation

### Profile
- **User profile** — full profile for yourself, public profile for another user

### 40 tools total

Discovery tools return a compact summary per tour by default (`compact=False` for the raw JSON, which can reach several hundred kilobytes).

## Setup

### 1. Configure credentials

```bash
cd komoot-mcp
cp .env.example .env
# Edit .env with your Komoot email and password
```

```env
KOMOOT_EMAIL=your.email@example.com
KOMOOT_PASSWORD=your_komoot_password
```

### 2. Install and run

```bash
uv sync
uv run python -m komoot_mcp.server
```

### 3. Add to Claude Desktop

```json
{
  "mcpServers": {
    "komoot": {
      "command": "uv",
      "args": ["--directory", "/path/to/komoot-mcp", "run", "python", "-m", "komoot_mcp.server"]
    }
  }
}
```

## Authentication

Basic Auth via Komoot's internal API (`/v006/account/email/{email}/`). Session token persisted in `~/.config/komoot-mcp/session.json` with automatic re-auth on 401. GET requests are retried on 429/502/503/504 with backoff (honouring `Retry-After`).

> **Note:** Komoot does not have an official public API. This server uses the same undocumented v007 REST API that the web frontend and all major third-party tools use. It could break if Komoot changes their internal API.

## Logging

JSON-lines logs in `~/.config/komoot-mcp/logs/komoot-mcp.log`. Set `KOMOOT_MCP_LOG_LEVEL=DEBUG` in `.env`.

## License

MIT
