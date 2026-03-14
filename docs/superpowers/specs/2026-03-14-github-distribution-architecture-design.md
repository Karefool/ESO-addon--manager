# ESO Power Lite - GitHub Distribution Architecture

## Overview

Migrate ESO Power Lite from a PostgreSQL-backed desktop app to a fully self-contained application that uses GitHub as its distribution and data infrastructure. This eliminates server costs, removes hardcoded credentials, fixes the .exe build, improves dependency resolution, and adds addon uninstall + app auto-update capabilities.

## Problem Statement

1. **Broken .exe build**: PyInstaller fails with `ModuleNotFoundError: No module named 'webview'` because `pywebview` is missing from requirements and hidden imports.
2. **Hardcoded database credentials**: Neon PostgreSQL connection string is embedded in source code — anyone who decompiles the .exe gets full database access.
3. **Incomplete dependency resolution**: Only `## DependsOn:` is parsed; `## OptionalDependsOn:` is ignored, causing addons like HodorReflexes to ship without required libs (LibCustomIcons, LibCustomNames).
4. **No addon uninstall**: The UI has a non-functional "Uninstall" button and no uninstall option in the browse view.
5. **No auto-update**: No mechanism to update the app itself or refresh addon metadata.
6. **Per-user API concern**: Without a central data cache, each user would hammer the MMOUI API directly.

## Security: Credential Cleanup

The Neon PostgreSQL connection string (including password) is currently hardcoded in `backend/app.py` and `backend/db.py`. As part of this migration:
1. Remove the credentials from all source files
2. Deprovision or rotate the Neon database password immediately after migration
3. If the repo has ever been public or will become public, treat the existing password as compromised

## Architecture

```
GitHub Actions (cron 2x daily)
  |-- Runs sync script: fetches MMOUI API -> builds addons.db (SQLite)
  |-- Publishes addons.db as GitHub Release asset (tag: "data-latest")
  |-- App .exe published as GitHub Release (tag: "v1.0.0", "v1.1.0", etc.)

ESO Power Lite (.exe) on user's machine
  |-- On startup:
  |     |-- Checks GitHub Releases for newer .exe version -> notifies user
  |     |-- Downloads/updates addons.db from "data-latest" release if stale (>24h)
  |-- Stores addons.db in %APPDATA%/ESO Power Lite/
  |-- FastAPI local server queries SQLite (built-in sqlite3, no psycopg2)
  |-- Addon installs: downloads ZIPs directly from MMOUI (unavoidable)
  |-- pywebview window renders the React frontend
```

### What gets removed

- `backend/db.py` — replaced by GitHub Actions sync script
- `psycopg2` dependency — replaced by built-in `sqlite3`
- Hardcoded Neon PostgreSQL credentials — removed and password rotated
- Direct MMOUI API calls for browsing/searching in the app — replaced by local SQLite

## Component Details

### 1. GitHub Actions Sync Workflow

**File**: `.github/workflows/sync-addons.yml`

- Runs on schedule (`cron: '0 6,18 * * *'` — twice daily at 6am/6pm UTC)
- Also supports `workflow_dispatch` for manual triggering
- Steps:
  1. Checkout repo
  2. Set up Python
  3. Install `requests`
  4. Run `scripts/sync_to_sqlite.py` (new file, derived from current `backend/db.py`)
  5. Delete existing `addons.db` asset from the `data-latest` release (GitHub doesn't support overwriting assets)
  6. Re-upload the new `addons.db` as a release asset to the `data-latest` tag

**Sync script** (`scripts/sync_to_sqlite.py`):
- Uses `api.py`'s `APIClient` to fetch all addons and categories from MMOUI
- Also fetches per-addon descriptions (batched with rate limiting) so the frontend can display them — this is a long-running step (~6000 addons) but acceptable in a CI context
- Writes to a local SQLite database

**SQLite Schema**:
```sql
CREATE TABLE categories (
  id TEXT PRIMARY KEY,
  title TEXT,
  icon TEXT,
  file_count INTEGER,
  parent_ids TEXT
);

CREATE TABLE addons (
  id TEXT PRIMARY KEY,
  category_id TEXT,
  version TEXT,
  last_updated INTEGER,
  name TEXT,
  author_name TEXT,
  file_info_url TEXT,
  download_total INTEGER,
  download_monthly INTEGER,
  favorite_total INTEGER,
  directories TEXT,          -- comma-separated folder names
  description TEXT           -- BBCode description from addon details
);

CREATE TABLE metadata (
  key TEXT PRIMARY KEY,
  value TEXT
);
-- Stores: key='last_synced', value=ISO timestamp

CREATE INDEX idx_addons_name ON addons(name COLLATE NOCASE);
CREATE INDEX idx_addons_category ON addons(category_id);
CREATE INDEX idx_addons_downloads ON addons(download_total);
CREATE INDEX idx_addons_directories ON addons(directories);
```

### 2. Backend Changes (backend/app.py)

**Remove**: All `psycopg2` imports, `DATABASE_URL`, `RealDictCursor` usage.

**Replace with**: `sqlite3` queries against the local `addons.db` file.

**SQLite-specific migration notes**:
- All `%s` parameter placeholders → `?` (sqlite3 convention)
- `ILIKE` → `LIKE` (SQLite `LIKE` is case-insensitive for ASCII by default)
- Configure `conn.row_factory = sqlite3.Row` so rows are accessible by column name (replaces `RealDictCursor`)
- `cursor.fetchone()['count']` → use `SELECT COUNT(*) as count` with `sqlite3.Row` factory

**Database location**: `%APPDATA%/ESO Power Lite/addons.db`
- On first run, if no local DB exists, download from GitHub Releases before serving any requests
- On subsequent runs, check DB file modification time; if >24 hours old, download fresh copy to a temp file then atomically rename to replace (avoids race conditions with concurrent reads)
- If no internet on first launch and no local DB exists: return empty results from API endpoints with an error message the frontend can display ("No addon data available — check your internet connection")

**New endpoints**:
- `DELETE /api/uninstall/{dir_name}` — removes addon folder from ESO AddOns directory (parameter is the directory name, not the display name)
- `GET /api/check-update` — checks GitHub Releases for newer app version, returns version info + download URL

**Modified endpoints**:
- `GET /api/addons` — same interface, backed by sqlite3 instead of psycopg2
- `GET /api/categories` — same interface, backed by sqlite3
- All other endpoints unchanged

### 3. Dependency Resolution Fix (manager.py)

**Problem**: `_resolve_dependencies()` only matches `## DependsOn:`, missing `## OptionalDependsOn:`. Also, `get_addon_by_name()` relies on MMOUI API data that may not include `UIDir`.

**Fix**:

a) **Parse both dependency types**:
```python
if line.startswith("## DependsOn:") or line.startswith("## OptionalDependsOn:"):
```

b) **Replace MMOUI API lookup with local SQLite search**:
Instead of calling `self.api.fetch_addons()` and iterating 6000+ addons in memory, query the local SQLite `directories` column. Use boundary-aware matching to avoid false positives:
```sql
SELECT * FROM addons
WHERE ',' || directories || ',' LIKE '%,LibCustomIcons,%'
LIMIT 1
```
This prevents `LibCustomIcons` from matching `LibCustomIconsData` by wrapping with comma boundaries.

c) **Fallback chain for addon lookup**:
1. Search SQLite `directories` column (boundary-aware LIKE match) — most reliable
2. Search SQLite `name` column (case-insensitive LIKE match)
3. If not found in SQLite, fall back to MMOUI API `fetch_addon_details` as last resort
4. Log warning if dependency cannot be resolved

d) **Keep `install_addon()` using MMOUI API for download URLs**: The SQLite DB doesn't store download URLs (they're in the detail endpoint). `install_addon()` will continue calling `self.api.fetch_addon_details(addon_id)` to get the `UIDownload` URL. This is the only remaining MMOUI API call in normal operation.

### 4. Addon Uninstall

**Backend** (`backend/app.py`):
```
DELETE /api/uninstall/{dir_name}
```
- Parameter is the **directory name** (e.g., `HodorReflexes`), not the display name (e.g., "Hodor Reflexes")
- Validates that `dir_name` is a simple directory name (no path traversal: no `/`, `\`, `..`)
- Checks the folder exists in the ESO AddOns directory
- Removes the entire addon directory (`shutil.rmtree`)
- Returns success/failure
- Does NOT remove dependencies (other addons may need them)

**Frontend** (`App.tsx`):

- **My Addons tab**: Wire up existing Uninstall button with `onClick` handler + confirmation dialog (`window.confirm`)
- **Discover tab**: For installed addons, replace static "Installed" badge with a button group showing "Installed" indicator + "Uninstall" option
- **Detail modal**: For installed addons, replace "Already Installed" button with "Uninstall" button
- After uninstall: refresh installed list and update addon cards
- **Remove non-functional UI**: Remove/disable the "Update All" button and the "Auto-update Addons on Launch" toggle since addon version comparison is out of scope for v1

### 5. Auto-Update Mechanism

**App version**: Add `VERSION = "1.0.0"` constant in a new `version.py` file.

**GitHub repo config**: Store owner/repo as constants:
```python
GITHUB_OWNER = "your-username"
GITHUB_REPO = "eso-addon-manager"
```

**Check on startup** (in `main.py`, before opening webview):
- Call GitHub Releases API: `GET https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest`
- Compare release tag against `VERSION`
- If newer: pass update info to frontend via a new `/api/check-update` endpoint
- Handle rate limiting (60 req/hr unauthenticated) and network errors gracefully — if the check fails, silently continue without blocking app startup

**Frontend notification**:
- If update available: show a dismissible banner at the top of the app with "New version available — Download" linking to the GitHub release page
- No auto-download/replace in v1 (replacing a running .exe on Windows is complex; link to release page is simpler and safer)

**Addon data update**:
- Handled transparently on startup (download fresh `addons.db` if stale)
- No user interaction needed

### 6. PyInstaller .exe Fix

**Root cause**: `pywebview` package name differs from its import name `webview`. PyInstaller can't auto-detect it.

**Fixes to `ESO_Power_Lite.spec`**:
```python
hiddenimports=['webview', 'clr_loader', 'pythonnet', 'bottle',
               'uvicorn', 'uvicorn.logging', 'uvicorn.loops',
               'uvicorn.loops.auto', 'uvicorn.protocols',
               'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
               'uvicorn.protocols.websockets',
               'uvicorn.protocols.websockets.auto',
               'uvicorn.lifespan', 'uvicorn.lifespan.on'],
```

Note: `bottle` is included because `pywebview` uses it internally as a lightweight HTTP backend on some platforms.

**Fixes to `requirements.txt`**: Add all missing packages:
```
pywebview
```
(`sqlite3` is built-in — no package needed)

**Remove from requirements**: `psycopg2` / `psycopg2-binary` (no longer needed)

**Build prerequisite**: `npm run build` must be run in `frontend/` before `pyinstaller` to produce `frontend/dist/`. The `build_windows.bat` script already handles this.

### 7. GitHub Repository Setup

- **Release `data-latest`**: Rolling release tag updated by GitHub Actions. Workflow deletes old asset then re-uploads (GitHub does not support overwriting release assets).
- **Versioned releases** (`v1.0.0`, etc.): Manual releases containing the built `.exe` (uploaded from local build or future CI)
- Repository should be public for unauthenticated GitHub API access from the app. If private, a GitHub token would need to be bundled (not recommended).

## Data Flow

### Addon browsing
```
User opens app
  -> FastAPI serves React frontend
  -> Frontend calls GET /api/addons?query=...
  -> FastAPI queries local SQLite addons.db (using sqlite3.Row factory)
  -> Returns results with is_installed flag
```

### Addon install
```
User clicks Install
  -> Frontend calls POST /api/install/{id}
  -> manager.py calls MMOUI API for addon details (download URL)
  -> Downloads ZIP, extracts to AddOns folder
  -> Parses manifest: DependsOn + OptionalDependsOn
  -> For each missing dep: searches local SQLite by directory name (boundary-aware LIKE)
  -> Recursively installs missing deps via MMOUI
```

### Addon uninstall
```
User clicks Uninstall -> confirmation dialog (window.confirm)
  -> Frontend calls DELETE /api/uninstall/{dir_name}
  -> Backend validates dir_name (no path traversal), removes folder via shutil.rmtree
  -> Frontend refreshes installed list
```

### App startup
```
main.py starts
  -> Check %APPDATA%/ESO Power Lite/addons.db modification time
  -> If missing: download from GitHub Releases "data-latest" (blocking)
  -> If exists but >24h old: download to temp file, atomic rename (non-blocking background)
  -> If no internet and no local DB: app starts with empty data + error banner
  -> Start FastAPI server (daemon thread)
  -> Check GitHub Releases for newer app version (non-blocking, fail silently)
  -> Open pywebview window
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `backend/app.py` | Modify | Replace psycopg2 with sqlite3, add uninstall + check-update endpoints |
| `backend/db.py` | Delete | No longer needed (replaced by GitHub Actions sync) |
| `manager.py` | Modify | Parse OptionalDependsOn, SQLite-based addon lookup for deps |
| `main.py` | Modify | Add startup DB freshness check + download logic |
| `version.py` | Create | App version constant + GitHub repo config |
| `requirements.txt` | Modify | Add pywebview, remove psycopg2 |
| `ESO_Power_Lite.spec` | Modify | Add hidden imports for webview/uvicorn |
| `scripts/sync_to_sqlite.py` | Create | SQLite sync script for GitHub Actions |
| `.github/workflows/sync-addons.yml` | Create | GitHub Actions workflow |
| `frontend/src/App.tsx` | Modify | Wire up uninstall buttons, add update banner, remove dead UI |

## Testing Strategy

- **Manual**: Build .exe, run it, verify addon browsing/install/uninstall/dependency resolution
- **Dependency resolution**: Install HodorReflexes specifically and verify LibCustomIcons, LibCustomNames, LibCombat2, LibRadialMenu all get pulled in
- **Uninstall**: Verify addon folder is removed, UI updates correctly in both views
- **Data sync**: Run sync script locally, verify SQLite DB is populated correctly with descriptions
- **Auto-update**: Mock a newer release tag and verify the notification appears
- **Offline**: Disconnect internet, verify app handles missing DB gracefully

## Out of Scope (Future)

- Auto-replace .exe on Windows (complex; v1 just links to release page)
- Addon version comparison / update detection for installed addons
- Backup/rollback of addon data
- CI/CD pipeline for building .exe in GitHub Actions
- SQLite schema migrations (DB is re-downloaded frequently, so schema changes are picked up automatically)
