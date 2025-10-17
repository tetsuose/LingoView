# LingoView Web Front-End

React + TypeScript (Vite) based UI for LingoView. Provides advanced video playback, subtitle highlighting, and API integration.

## Development

```bash
pnpm install
pnpm --filter web dev
```

The app expects the FastAPI backend to run on `http://localhost:8000` (start it via `../python/run_api.sh`). You can override the API origin by setting `VITE_API_BASE_URL`.

## Production build

```bash
pnpm --filter web build
```

Build output is generated into `web/dist`.
