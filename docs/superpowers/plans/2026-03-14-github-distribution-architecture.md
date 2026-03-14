# GitHub Distribution Architecture Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate ESO Power Lite to a self-contained desktop app using GitHub for data distribution and auto-updates, fixing the .exe build, dependency resolution, and adding uninstall functionality.

**Architecture:** The app stores addon metadata in a local SQLite database downloaded from GitHub Releases (synced 2x/day by GitHub Actions). No remote database credentials ship with the app. Addon installs still download ZIPs from MMOUI directly. The app checks GitHub Releases for self-updates on startup.

**Tech Stack:** Python (FastAPI, uvicorn, pywebview, sqlite3), React/TypeScript (Vite, Tailwind), PyInstaller, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-03-14-github-distribution-architecture-design.md`

**Important:** This project is not currently a git repo. Task 1 initializes it. All commit steps assume the repo is initialized.

---

## Chunk 1: Foundation (Tasks 1-3)

### Task 1: Initialize Git Repo + Create version.py + Update requirements.txt

**Files:**
- Create: `.gitignore`
- Create: `version.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Initialize git repo**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
git init
```

- [ ] **Step 2: Create .gitignore**

Create `.gitignore`:
```
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
node_modules/
frontend/dist/
*.db
.env
*.exe
venv/
.venv/
```

- [ ] **Step 3: Create version.py**

Create `version.py` in the project root:
```python
VERSION = "1.0.0"
GITHUB_OWNER = ""  # TODO: fill in after GitHub repo is created
GITHUB_REPO = "eso-addon-manager"
```

Note: `GITHUB_OWNER` will be filled in once the user creates their GitHub repo.

- [ ] **Step 4: Update requirements.txt**

Replace contents of `requirements.txt` with:
```
certifi==2024.2.2
charset-normalizer==3.3.2
colorama==0.4.6
idna==3.6
markdown-it-py==3.0.0
mdurl==0.1.2
Pygments==2.17.2
requests==2.31.0
rich==13.7.1
urllib3==2.2.1
fastapi
uvicorn
pywebview
```

Key changes: added `pywebview`, removed `psycopg2` (not present but making explicit).

- [ ] **Step 5: Commit**

```bash
git add .gitignore version.py requirements.txt
git commit -m "chore: init repo, add version.py, add pywebview to requirements"
```

---

### Task 2: Create SQLite Sync Script

This script runs in GitHub Actions to fetch all addon data from MMOUI and produce a SQLite database file.

**Files:**
- Create: `scripts/sync_to_sqlite.py`

**Depends on:** `api.py` (existing, unchanged)

- [ ] **Step 1: Create scripts directory**

```bash
mkdir -p scripts
```

- [ ] **Step 2: Create sync_to_sqlite.py**

Create `scripts/sync_to_sqlite.py`:
```python
"""
Sync MMOUI addon data to a local SQLite database.
Run by GitHub Actions on a schedule, or locally for testing.
Produces addons.db in the current working directory.
"""
import sqlite3
import os
import sys
import time
from datetime import datetime, timezone

# Add project root to path so we can import api.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api import APIClient


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'addons.db')


def create_schema(conn):
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            title TEXT,
            icon TEXT,
            file_count INTEGER,
            parent_ids TEXT
        );

        CREATE TABLE IF NOT EXISTS addons (
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
            directories TEXT,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_addons_name ON addons(name COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_addons_category ON addons(category_id);
        CREATE INDEX IF NOT EXISTS idx_addons_downloads ON addons(download_total);
        CREATE INDEX IF NOT EXISTS idx_addons_directories ON addons(directories);
    ''')
    conn.commit()


def sync_categories(conn, api):
    print("Fetching categories...")
    categories = api.fetch_categories()
    cursor = conn.cursor()

    for cat in categories:
        parent_ids = cat.get('UICATParentIDs', '')
        if isinstance(parent_ids, list):
            parent_ids = ",".join(parent_ids)

        cursor.execute('''
            INSERT OR REPLACE INTO categories (id, title, icon, file_count, parent_ids)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            cat.get('UICATID'),
            cat.get('UICATTitle'),
            cat.get('UICATICON'),
            int(cat.get('UICATFileCount', 0)),
            str(parent_ids)
        ))

    conn.commit()
    print(f"Synced {len(categories)} categories.")


def sync_addons(conn, api):
    print("Fetching addon list...")
    addons = api.fetch_addons()
    cursor = conn.cursor()

    print(f"Syncing {len(addons)} addons (metadata only first pass)...")
    for addon in addons:
        dl_total = str(addon.get('UIDownloadTotal', '0')).replace(',', '')
        dl_monthly = str(addon.get('UIDownloadMonthly', '0')).replace(',', '')
        fav_total = str(addon.get('UIFavoriteTotal', '0')).replace(',', '')

        directories = addon.get('UIDir', [])
        if isinstance(directories, list):
            directories = ",".join(directories)

        cursor.execute('''
            INSERT OR REPLACE INTO addons
            (id, category_id, version, last_updated, name, author_name,
             file_info_url, download_total, download_monthly, favorite_total, directories)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            addon.get('UID'),
            addon.get('UICATID'),
            addon.get('UIVersion'),
            int(addon.get('UIDate', 0)),
            addon.get('UIName'),
            addon.get('UIAuthorName'),
            addon.get('UIFileInfoURL'),
            int(dl_total) if dl_total.isdigit() else 0,
            int(dl_monthly) if dl_monthly.isdigit() else 0,
            int(fav_total) if fav_total.isdigit() else 0,
            directories
        ))

    conn.commit()
    print("Metadata sync complete.")

    # Second pass: fetch descriptions (slow but acceptable in CI)
    print("Fetching addon descriptions (this will take a while)...")
    addon_ids = [a.get('UID') for a in addons if a.get('UID')]
    fetched = 0
    errors = 0

    for addon_id in addon_ids:
        try:
            details = api.fetch_addon_details(addon_id)
            description = details.get('UIDescription', '') if details else ''
            cursor.execute(
                'UPDATE addons SET description = ? WHERE id = ?',
                (description, addon_id)
            )
            fetched += 1
            if fetched % 100 == 0:
                conn.commit()
                print(f"  Fetched {fetched}/{len(addon_ids)} descriptions...")
            # Rate limit: small delay to avoid hammering MMOUI
            time.sleep(0.1)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Warning: failed to fetch description for {addon_id}: {e}")

    conn.commit()
    print(f"Description sync complete. Fetched: {fetched}, Errors: {errors}")


def update_metadata(conn):
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        'INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)',
        ('last_synced', now)
    )
    conn.commit()
    print(f"Metadata updated: last_synced = {now}")


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH

    # Remove old DB if it exists to start fresh
    if os.path.exists(output_path):
        os.remove(output_path)

    print(f"Creating database at {output_path}")
    conn = sqlite3.connect(output_path)

    try:
        api = APIClient()
        api.initialize()

        create_schema(conn)
        sync_categories(conn, api)
        sync_addons(conn, api)
        update_metadata(conn)

        print("Sync complete!")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Verify sync script runs locally (partial test)**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
python scripts/sync_to_sqlite.py test_addons.db
```

Let it run for a minute or two to verify it creates the DB and starts fetching. You can Ctrl+C after seeing some progress. Then verify:

```bash
python -c "import sqlite3; conn = sqlite3.connect('test_addons.db'); print(conn.execute('SELECT COUNT(*) FROM addons').fetchone()); print(conn.execute('SELECT COUNT(*) FROM categories').fetchone())"
```

Expected: non-zero counts for both tables. Clean up:
```bash
rm test_addons.db
```

- [ ] **Step 4: Commit**

```bash
git add scripts/sync_to_sqlite.py
git commit -m "feat: add SQLite sync script for GitHub Actions"
```

---

### Task 3: Migrate backend/app.py from PostgreSQL to SQLite

This is the core backend migration. Replace all psycopg2 usage with sqlite3.

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Rewrite backend/app.py**

Replace the entire contents of `backend/app.py` with:

```python
import sqlite3
import shutil
import re
import os
import sys

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from manager import AddonManager

app = FastAPI(title="ESO Power Lite API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database location: %APPDATA%/ESO Power Lite/addons.db
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ESO Power Lite')
DB_PATH = os.path.join(APPDATA_DIR, 'addons.db')


def get_db_connection():
    """Get a SQLite connection with Row factory for dict-like access."""
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


manager = AddonManager()


@app.get("/api/categories")
def get_categories():
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM categories ORDER BY title ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@app.get("/api/addons")
def get_addons(
    query: Optional[str] = None,
    category_id: Optional[str] = None,
    sort_by: str = Query("download_total", pattern="^(download_total|name|last_updated|favorite_total)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    conn = get_db_connection()
    if not conn:
        return {"total": 0, "page": page, "limit": limit, "addons": []}
    try:
        cursor = conn.cursor()
        installed_dirs = set(manager.get_installed_addons())

        where_clauses = []
        params = []

        if query:
            where_clauses.append("(name LIKE ? OR description LIKE ? OR author_name LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

        if category_id:
            where_clauses.append("category_id = ?")
            params.append(category_id)

        where_stmt = ""
        if where_clauses:
            where_stmt = "WHERE " + " AND ".join(where_clauses)

        # Count total
        count_query = f"SELECT COUNT(*) as count FROM addons {where_stmt}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()['count']

        # Fetch paginated
        offset = (page - 1) * limit
        sql = f"""
            SELECT * FROM addons
            {where_stmt}
            ORDER BY {sort_by} {'ASC' if order == 'asc' else 'DESC'}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor.execute(sql, params)
        raw_addons = cursor.fetchall()

        addons = []
        for row in raw_addons:
            addon = dict(row)
            addon_dirs = set(addon['directories'].split(',')) if addon.get('directories') else set()
            addon['is_installed'] = bool(addon_dirs.intersection(installed_dirs))
            addons.append(addon)

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "addons": addons
        }
    finally:
        conn.close()


@app.get("/api/installed")
def get_installed():
    return {"installed": manager.get_installed_addons()}


@app.post("/api/install/{addon_id}")
def install_addon(addon_id: str):
    try:
        manager.install_addon(addon_id)
        return {"status": "success", "message": f"Installed addon ID {addon_id} and its dependencies."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/uninstall/{dir_name}")
def uninstall_addon(dir_name: str):
    # Validate: no path traversal characters
    if re.search(r'[/\\]|\.\.', dir_name):
        raise HTTPException(status_code=400, detail="Invalid addon directory name.")

    addon_path = manager.addons_dir / dir_name
    if not addon_path.exists() or not addon_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Addon directory '{dir_name}' not found.")

    try:
        shutil.rmtree(addon_path)
        return {"status": "success", "message": f"Uninstalled {dir_name}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/check-update")
def check_update():
    """Returns cached update info set by main.py on startup."""
    from version import VERSION
    return {
        "current_version": VERSION,
        "update_available": getattr(app.state, 'update_available', False),
        "latest_version": getattr(app.state, 'latest_version', VERSION),
        "download_url": getattr(app.state, 'update_download_url', ''),
    }


from fastapi.staticfiles import StaticFiles
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')
if os.path.exists(frontend_dist):
    app.mount('/', StaticFiles(directory=frontend_dist, html=True), name='frontend')
```

- [ ] **Step 2: Verify the module imports correctly**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
python -c "from backend.app import app; print('Backend imports OK')"
```

Expected: "Backend imports OK" (may warn about missing DB, that's fine).

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat: migrate backend from PostgreSQL to SQLite"
```

---

## Chunk 2: Dependency Resolution + Manager Fix (Task 4)

### Task 4: Fix Dependency Resolution in manager.py

**Files:**
- Modify: `manager.py`

- [ ] **Step 1: Rewrite manager.py with SQLite-backed dependency resolution**

Replace the entire contents of `manager.py` with:

```python
import os
import re
import sqlite3
import zipfile
import tempfile
from pathlib import Path
from typing import List, Dict, Set, Optional

from api import APIClient

# Database path: same as backend/app.py
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ESO Power Lite')
DB_PATH = os.path.join(APPDATA_DIR, 'addons.db')


class AddonManager:
    def __init__(self, addons_dir: Optional[str] = None):
        self.api = APIClient()
        if addons_dir is None:
            self.addons_dir = Path.home() / "Documents" / "Elder Scrolls Online" / "live" / "AddOns"
        else:
            self.addons_dir = Path(addons_dir)

        self.addons_dir.mkdir(parents=True, exist_ok=True)
        self.api.initialize()

    def _get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Get a SQLite connection for dependency lookups."""
        if not os.path.exists(DB_PATH):
            return None
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _download_file(self, url: str) -> str:
        """Downloads a file to a temp directory and returns the path."""
        response = self.api.session.get(url, stream=True, timeout=30)
        response.raise_for_status()

        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, "addon.zip")
        with open(temp_file, 'wb') as out_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    out_file.write(chunk)
        return temp_file

    def find_addon_by_directory(self, dir_name: str) -> Optional[Dict]:
        """Search local SQLite for an addon by its directory name.
        Uses boundary-aware matching to avoid false positives."""
        conn = self._get_db_connection()
        if not conn:
            return self._find_addon_by_name_api(dir_name)

        try:
            cursor = conn.cursor()

            # Strategy 1: boundary-aware directory match (most reliable)
            cursor.execute(
                "SELECT * FROM addons WHERE ',' || directories || ',' LIKE ? LIMIT 1",
                (f"%,{dir_name},%",)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Strategy 2: case-insensitive name match
            cursor.execute(
                "SELECT * FROM addons WHERE name LIKE ? LIMIT 1",
                (dir_name,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)

            # Strategy 3: fall back to MMOUI API
            return self._find_addon_by_name_api(dir_name)
        finally:
            conn.close()

    def _find_addon_by_name_api(self, name: str) -> Optional[Dict]:
        """Fallback: search MMOUI API for an addon by name."""
        try:
            all_addons = self.api.fetch_addons()
            for addon in all_addons:
                if addon.get('UIName', '').lower() == name.lower():
                    return addon
                dirs = addon.get('UIDir', [])
                if any(d.lower() == name.lower() for d in dirs):
                    return addon
        except Exception as e:
            print(f"  API fallback search failed for {name}: {e}")
        return None

    def search_addons(self, query: str) -> List[Dict]:
        """Search for addons matching the query using local SQLite."""
        conn = self._get_db_connection()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM addons WHERE name LIKE ? OR directories LIKE ? LIMIT 50",
                (f"%{query}%", f"%{query}%")
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_addon_by_name(self, name: str) -> Optional[Dict]:
        """Find addon by name or directory. Uses SQLite first, API fallback."""
        return self.find_addon_by_directory(name)

    def install_addon(self, addon_id: str, downloaded_set: Set[str] = None):
        if downloaded_set is None:
            downloaded_set = set()

        if addon_id in downloaded_set:
            return

        downloaded_set.add(addon_id)

        details = self.api.fetch_addon_details(addon_id)
        if not details:
            print(f"Could not fetch details for addon ID {addon_id}")
            return

        download_url = details.get("UIDownload")
        if not download_url:
            print(f"No download URL found for {details.get('UIName')}")
            return

        print(f"Downloading {details.get('UIName')}...")
        zip_path = self._download_file(download_url)

        print(f"Extracting to {self.addons_dir}...")
        dirs = set()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                member_path = Path(member)
                if '..' in member_path.parts or member_path.is_absolute():
                    print(f"WARNING: Skipping malicious path in zip: {member}")
                    continue
                zip_ref.extract(member, self.addons_dir)
                root = member.split('/')[0].split('\\')[0]
                if root:
                    dirs.add(root)

        # Clean up temp zip
        os.remove(zip_path)
        os.rmdir(os.path.dirname(zip_path))

        # Check dependencies
        for d in dirs:
            manifest_path_txt = self.addons_dir / d / f"{d}.txt"
            manifest_path_addon = self.addons_dir / d / f"{d}.addon"
            manifest_path = manifest_path_txt if manifest_path_txt.exists() else manifest_path_addon

            if manifest_path.exists():
                self._resolve_dependencies(manifest_path, downloaded_set)

    def _resolve_dependencies(self, manifest_path: Path, downloaded_set: Set[str]):
        """Parse DependsOn AND OptionalDependsOn, install missing dependencies."""
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(manifest_path, 'r', encoding='latin-1') as f:
                content = f.read()

        depends_on = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("## DependsOn:") or line.startswith("## OptionalDependsOn:"):
                deps_str = line.split(":", 1)[1].strip()
                deps = [d.strip() for d in deps_str.split()]
                for dep in deps:
                    clean_dep = re.sub(r'[><=]+[\w\.-]+', '', dep).strip()
                    if clean_dep:
                        depends_on.append(clean_dep)

        for dep in depends_on:
            dep_path = self.addons_dir / dep
            if not dep_path.exists():
                print(f"Missing dependency: {dep}. Searching...")
                addon = self.find_addon_by_directory(dep)
                if addon:
                    addon_id = addon.get('UID') or addon.get('id')
                    print(f"Found {dep} (ID: {addon_id}). Installing...")
                    self.install_addon(addon_id, downloaded_set)
                else:
                    print(f"WARNING: Could not find dependency '{dep}' in database or ESOUI.")

    def get_installed_addons(self) -> List[str]:
        installed = []
        if self.addons_dir.exists():
            for item in self.addons_dir.iterdir():
                if item.is_dir():
                    manifest_txt = item / f"{item.name}.txt"
                    manifest_addon = item / f"{item.name}.addon"
                    if manifest_txt.exists() or manifest_addon.exists():
                        installed.append(item.name)
        return installed
```

Key changes:
- `_resolve_dependencies` now matches both `## DependsOn:` and `## OptionalDependsOn:`
- New `find_addon_by_directory()` searches SQLite first (boundary-aware LIKE), then falls back to API
- `get_addon_by_name()` now delegates to `find_addon_by_directory()`
- `DB_PATH` constant shared with backend for consistency

- [ ] **Step 2: Verify manager imports correctly**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
python -c "from manager import AddonManager; print('Manager imports OK')"
```

Expected: "Manager imports OK"

- [ ] **Step 3: Commit**

```bash
git add manager.py
git commit -m "fix: parse OptionalDependsOn + SQLite-backed dependency lookup"
```

---

## Chunk 3: Startup Logic + main.py (Task 5)

### Task 5: Update main.py with DB Download + Auto-Update Check

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Rewrite main.py**

Replace the entire contents of `main.py` with:

```python
import os
import sys
import threading
import time
import tempfile
import requests
import uvicorn
import webview

from version import VERSION, GITHUB_OWNER, GITHUB_REPO

# App data directory
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ESO Power Lite')
DB_PATH = os.path.join(APPDATA_DIR, 'addons.db')
DB_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours


def ensure_appdata_dir():
    os.makedirs(APPDATA_DIR, exist_ok=True)


def db_is_stale():
    """Check if the local DB is missing or older than 24 hours."""
    if not os.path.exists(DB_PATH):
        return True
    mtime = os.path.getmtime(DB_PATH)
    age = time.time() - mtime
    return age > DB_MAX_AGE_SECONDS


def download_db(blocking=True):
    """Download addons.db from GitHub Releases 'data-latest' tag."""
    if not GITHUB_OWNER:
        print("GITHUB_OWNER not configured in version.py, skipping DB download.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tags/data-latest"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        release = resp.json()

        # Find the addons.db asset
        asset_url = None
        for asset in release.get('assets', []):
            if asset['name'] == 'addons.db':
                asset_url = asset['browser_download_url']
                break

        if not asset_url:
            print("No addons.db asset found in data-latest release.")
            return False

        print(f"Downloading addon database...")
        db_resp = requests.get(asset_url, timeout=60, stream=True)
        db_resp.raise_for_status()

        # Download to temp file first, then atomic rename
        temp_fd, temp_path = tempfile.mkstemp(dir=APPDATA_DIR, suffix='.db.tmp')
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                for chunk in db_resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            # Atomic replace (on Windows, need to remove target first)
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            os.rename(temp_path, DB_PATH)
            print("Addon database updated.")
            return True
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    except Exception as e:
        print(f"Failed to download addon database: {e}")
        return False


def check_app_update(app):
    """Check GitHub Releases for a newer app version. Store result on app.state."""
    if not GITHUB_OWNER:
        return

    try:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 403:  # Rate limited
            return
        resp.raise_for_status()
        release = resp.json()

        latest_tag = release.get('tag_name', '').lstrip('v')
        # Simple semver comparison: split into parts and compare numerically
        def parse_version(v):
            try:
                return tuple(int(x) for x in v.split('.'))
            except (ValueError, AttributeError):
                return (0,)

        if latest_tag and parse_version(latest_tag) > parse_version(VERSION):
            app.state.update_available = True
            app.state.latest_version = latest_tag
            app.state.update_download_url = release.get('html_url', '')
            print(f"Update available: v{latest_tag}")
    except Exception as e:
        print(f"Update check failed (non-blocking): {e}")


def start_server():
    from backend.app import app

    # Check for app updates (non-blocking, stores on app.state)
    check_app_update(app)

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")


if __name__ == '__main__':
    # Ensure app data directory exists
    ensure_appdata_dir()

    # Download/update addon database if needed
    if db_is_stale():
        if not os.path.exists(DB_PATH):
            # First run: blocking download
            print("First run — downloading addon database...")
            download_db(blocking=True)
        else:
            # Stale: background download
            threading.Thread(target=download_db, daemon=True).start()

    # Start the local FastAPI server daemon
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # Wait for the backend to initialize
    time.sleep(1.5)

    # Launch the native webview window
    webview.create_window(
        title="ESO Power Lite",
        url="http://127.0.0.1:8000",
        width=1200,
        height=800,
        min_size=(1024, 768),
        background_color="#09090b"
    )

    webview.start()
```

- [ ] **Step 2: Verify main.py imports correctly**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
python -c "import main; print('main.py imports OK')" 2>&1 | head -5
```

This may error on `webview.start()` without a display, but imports should resolve.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add startup DB download + auto-update check"
```

---

## Chunk 4: Frontend Updates (Task 6)

### Task 6: Wire Up Uninstall, Update Banner, Remove Dead UI

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update App.tsx**

Replace the entire contents of `frontend/src/App.tsx` with:

```tsx
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Compass, Package, Settings, Download, X, RefreshCw, HardDrive, Trash2 } from 'lucide-react';
import { parseBBCode, stripBBCode } from './bbcode';
import './index.css';

const API_BASE = 'http://localhost:8000/api';

interface Category {
  id: string;
  title: string;
  file_count: number;
}

interface Addon {
  id: string;
  name: string;
  author_name: string;
  download_total: number;
  description: string;
  version: string;
  is_installed: boolean;
  directories: string;  // comma-separated folder names
}

interface UpdateInfo {
  update_available: boolean;
  latest_version: string;
  download_url: string;
  current_version: string;
}

function App() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [addons, setAddons] = useState<Addon[]>([]);
  const [installed, setInstalled] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [sort, setSort] = useState('download_total');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallingName, setUninstallingName] = useState<string | null>(null);
  const [view, setView] = useState<'discover' | 'installed' | 'settings'>('discover');
  const [selectedAddon, setSelectedAddon] = useState<Addon | null>(null);
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateDismissed, setUpdateDismissed] = useState(false);

  useEffect(() => {
    fetchCategories();
    fetchInstalled();
    checkForUpdate();

    const handleFocus = () => {
      fetchInstalled();
      if (view === 'discover') fetchAddons();
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, []);

  useEffect(() => {
    if (view === 'discover') {
      fetchAddons();
    }
  }, [search, activeCategory, sort, page, view]);

  const fetchCategories = async () => {
    try {
      const res = await fetch(`${API_BASE}/categories`);
      const data = await res.json();
      setCategories(data);
    } catch (err) {
      console.error('Failed to fetch categories:', err);
    }
  };

  const fetchInstalled = async () => {
    try {
      const res = await fetch(`${API_BASE}/installed`);
      const data = await res.json();
      setInstalled(data.installed);
    } catch (err) {
      console.error('Failed to fetch installed addons:', err);
    }
  };

  const fetchAddons = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '20',
        sort_by: sort,
        order: 'desc'
      });
      if (search) params.append('query', search);
      if (activeCategory) params.append('category_id', activeCategory);

      const res = await fetch(`${API_BASE}/addons?${params}`);
      const data = await res.json();
      setAddons(data.addons);
      setTotalPages(Math.ceil(data.total / data.limit));
    } catch (err) {
      console.error('Failed to fetch addons:', err);
    } finally {
      setLoading(false);
    }
  };

  const checkForUpdate = async () => {
    try {
      const res = await fetch(`${API_BASE}/check-update`);
      const data: UpdateInfo = await res.json();
      if (data.update_available) {
        setUpdateInfo(data);
      }
    } catch (err) {
      // Non-critical, ignore
    }
  };

  const installAddon = async (id: string, name: string) => {
    setInstallingId(id);
    try {
      const res = await fetch(`${API_BASE}/install/${id}`, { method: 'POST' });
      if (res.ok) {
        fetchInstalled();
        setAddons(prev => prev.map(a => a.id === id ? { ...a, is_installed: true } : a));
        if (selectedAddon?.id === id) {
          setSelectedAddon(prev => prev ? { ...prev, is_installed: true } : null);
        }
      } else {
        alert(`Failed to install ${name}`);
      }
    } catch (err) {
      alert(`Error installing ${name}`);
    } finally {
      setInstallingId(null);
    }
  };

  const uninstallAddon = async (dirName: string) => {
    if (!window.confirm(`Are you sure you want to uninstall "${dirName}"? This will delete the addon folder.`)) {
      return;
    }

    setUninstallingName(dirName);
    try {
      const res = await fetch(`${API_BASE}/uninstall/${dirName}`, { method: 'DELETE' });
      if (res.ok) {
        fetchInstalled();
        setAddons(prev => prev.map(a => {
          const addonDirs = a.name === dirName ? [dirName] : [];
          // We can't perfectly match here, so just refresh
          return a;
        }));
        // Refresh addon list to update is_installed flags
        if (view === 'discover') fetchAddons();
        if (selectedAddon) {
          setSelectedAddon(prev => prev ? { ...prev, is_installed: false } : null);
        }
      } else {
        const data = await res.json();
        alert(`Failed to uninstall: ${data.detail || 'Unknown error'}`);
      }
    } catch (err) {
      alert(`Error uninstalling ${dirName}`);
    } finally {
      setUninstallingName(null);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#09090b] text-zinc-100 overflow-hidden font-sans selection:bg-blue-500/30">

      {/* Sidebar */}
      <aside className="w-64 border-r border-white/5 bg-[#09090b]/80 backdrop-blur-xl flex flex-col z-20 sticky top-0">
        <div className="p-6">
          <h1 className="text-xl font-bold tracking-tighter bg-gradient-to-br from-white to-white/50 bg-clip-text text-transparent flex items-center gap-2">
            <Package className="w-5 h-5 text-blue-500" />
            ESO Power Lite
          </h1>
        </div>

        <nav className="flex-1 px-4 space-y-1">
          <button
            onClick={() => setView('discover')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              view === 'discover'
                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]'
                : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
            }`}
          >
            <Compass className="w-4 h-4" /> Discover Addons
          </button>

          <button
            onClick={() => setView('installed')}
            className={`w-full flex flex-row justify-between items-center px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              view === 'installed'
                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]'
                : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
            }`}
          >
            <span className="flex items-center gap-3"><HardDrive className="w-4 h-4" /> My Addons</span>
            {installed.length > 0 && (
              <span className="bg-white/10 text-zinc-300 text-xs py-0.5 px-2 rounded-full border border-white/5">
                {installed.length}
              </span>
            )}
          </button>

          <div className="pt-6 pb-2">
            <p className="text-xs font-semibold text-zinc-600 uppercase tracking-wider px-3">Categories</p>
          </div>
          <div className="space-y-0.5 max-h-[40vh] overflow-y-auto pr-1 pb-4 custom-scroll">
            <button
              onClick={() => { setActiveCategory(null); setPage(1); setView('discover'); }}
              className={`w-full text-left px-3 py-1.5 rounded-md text-sm transition-colors ${
                !activeCategory && view === 'discover' ? 'text-zinc-100 bg-white/5' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'
              }`}
            >
              All Categories
            </button>
            {categories.map(c => (
              <button
                key={c.id}
                onClick={() => { setActiveCategory(c.id); setPage(1); setView('discover'); }}
                className={`w-full flex justify-between items-center px-3 py-1.5 rounded-md text-sm transition-colors ${
                  activeCategory === c.id && view === 'discover' ? 'text-zinc-100 bg-white/5' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/5'
                }`}
              >
                <span className="truncate pr-2">{c.title}</span>
                <span className="text-xs opacity-50">{c.file_count}</span>
              </button>
            ))}
          </div>
        </nav>

        <div className="p-4 border-t border-white/5">
          <button
            onClick={() => setView('settings')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
              view === 'settings'
              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]'
              : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5'
            }`}
          >
            <Settings className="w-4 h-4" /> Settings
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 bg-gradient-to-br from-[#09090b] to-[#0c0c10] relative">
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 brightness-100 contrast-150 mix-blend-overlay pointer-events-none z-0"></div>

        {/* Update Banner */}
        {updateInfo && !updateDismissed && (
          <div className="relative z-20 bg-blue-600/20 border-b border-blue-500/30 px-8 py-2.5 flex items-center justify-between">
            <p className="text-sm text-blue-200">
              New version <strong>v{updateInfo.latest_version}</strong> is available (you have v{updateInfo.current_version}).
              <a
                href={updateInfo.download_url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 underline text-blue-300 hover:text-white transition-colors"
                onClick={(e) => {
                  e.preventDefault();
                  // pywebview: open in system browser
                  window.open(updateInfo.download_url, '_blank');
                }}
              >
                Download update
              </a>
            </p>
            <button
              onClick={() => setUpdateDismissed(true)}
              className="text-blue-300 hover:text-white transition-colors p-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Topbar */}
        <header className="h-16 border-b border-white/5 bg-white/[0.02] backdrop-blur-md flex items-center justify-between px-8 z-10 shrink-0">
          <div className="w-full max-w-md relative">
            {view === 'discover' && (
              <>
                <Search className="w-4 h-4 absolute left-3 text-zinc-500 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search addons..."
                  className="w-full bg-zinc-900/50 border border-white/10 rounded-full py-1.5 pl-10 pr-4 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50 transition-all shadow-inner"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    setPage(1);
                  }}
                />
              </>
            )}
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => { fetchInstalled(); if(view==='discover') fetchAddons(); }}
              className="text-zinc-400 hover:text-zinc-100 transition-colors p-2"
              title="Refresh Local Files"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-8 relative z-10 custom-scroll">

          {view === 'discover' && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-7xl mx-auto">
              <div className="flex justify-between items-end mb-8">
                <div>
                  <h2 className="text-3xl font-bold tracking-tight text-zinc-100">Discover</h2>
                  <p className="text-sm text-zinc-400 mt-1">Browse and install the best addons for Elder Scrolls Online.</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-zinc-500 font-medium uppercase tracking-wider">Sort by</span>
                  <select
                    value={sort}
                    onChange={(e) => { setSort(e.target.value); setPage(1); }}
                    className="bg-zinc-900 border border-white/10 rounded-lg py-1.5 px-3 text-sm text-zinc-300 focus:outline-none focus:border-blue-500 sm:text-sm"
                  >
                    <option value="download_total">Most Downloaded</option>
                    <option value="last_updated">Recently Updated</option>
                    <option value="favorite_total">Most Favorited</option>
                  </select>
                </div>
              </div>

              {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 animate-pulse">
                  {[...Array(12)].map((_, i) => (
                    <div key={i} className="h-[220px] rounded-xl bg-white/5 border border-white/5"></div>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {addons.map((addon, i) => (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.95 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: i * 0.05 }}
                      key={addon.id}
                      onClick={() => setSelectedAddon(addon)}
                      className="group relative flex flex-col bg-white/[0.02] border border-white/5 rounded-xl p-5 hover:bg-white/[0.04] hover:border-white/10 transition-all cursor-pointer overflow-hidden shadow-lg shadow-black/20"
                    >
                      <div className="absolute inset-0 bg-gradient-to-tr from-blue-500/0 via-blue-500/0 to-blue-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>

                      <div className="flex-1">
                        <h3 className="text-base font-semibold text-zinc-100 line-clamp-1 group-hover:text-blue-400 transition-colors" dangerouslySetInnerHTML={{ __html: addon.name }} />
                        <p className="text-xs text-zinc-500 mt-0.5 mb-3">by {addon.author_name}</p>
                        <p className="text-sm text-zinc-400 line-clamp-3 leading-relaxed">{stripBBCode(addon.description) || "No description available."}</p>
                      </div>

                      <div className="mt-5 flex items-center justify-between pt-4 border-t border-white/5 relative z-10">
                        <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                          <Download className="w-3.5 h-3.5" />
                          <span>{(addon.download_total / 1000).toFixed(1)}k</span>
                        </div>

                        {addon.is_installed ? (
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-1 rounded-md text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">
                              Installed
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                const dirs = addon.directories ? addon.directories.split(',') : [];
                                const matchedDir = dirs.find(d => installed.includes(d));
                                if (matchedDir) {
                                  uninstallAddon(matchedDir);
                                } else {
                                  alert('Could not determine addon directory. Please uninstall from My Addons tab.');
                                }
                              }}
                              className="p-1 rounded-md text-zinc-500 hover:text-red-400 hover:bg-red-400/10 transition-colors"
                              title="Uninstall"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <button
                            disabled={installingId === addon.id}
                            onClick={(e) => {
                              e.stopPropagation();
                              installAddon(addon.id, addon.name);
                            }}
                            className="px-3 py-1 rounded-md text-xs font-medium bg-white/10 text-zinc-100 hover:bg-blue-600 hover:text-white transition-colors border border-white/5 disabled:opacity-50"
                          >
                            {installingId === addon.id ? 'Loading...' : 'Install'}
                          </button>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}

              {!loading && totalPages > 1 && (
                <div className="flex items-center justify-center gap-4 mt-12 mb-8">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="px-4 py-2 rounded-lg bg-zinc-900 border border-white/10 text-sm text-zinc-300 hover:bg-white/5 disabled:opacity-50 transition-colors">Previous</button>
                  <span className="text-sm text-zinc-500">Page <strong className="text-zinc-300">{page}</strong> of <strong className="text-zinc-300">{totalPages}</strong></span>
                  <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="px-4 py-2 rounded-lg bg-zinc-900 border border-white/10 text-sm text-zinc-300 hover:bg-white/5 disabled:opacity-50 transition-colors">Next</button>
                </div>
              )}
            </motion.div>
          )}

          {view === 'installed' && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-5xl mx-auto">
              <div className="flex justify-between items-end mb-8">
                <div>
                  <h2 className="text-3xl font-bold tracking-tight text-zinc-100">My Addons</h2>
                  <p className="text-sm text-zinc-400 mt-1">Addons synced with your local AddOns folder.</p>
                </div>
              </div>

              {installed.length === 0 ? (
                <div className="text-center py-20 px-4 border border-white/5 border-dashed rounded-2xl bg-white/[0.01]">
                  <HardDrive className="w-12 h-12 text-zinc-600 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-zinc-300">No addons found</h3>
                  <p className="text-sm text-zinc-500 mt-1">Install some addons from the Discover tab to see them here.</p>
                </div>
              ) : (
                <div className="bg-[#0c0c10] border border-white/10 rounded-2xl overflow-hidden shadow-2xl">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead className="lowercase text-zinc-500 bg-white/5 border-b border-white/10">
                      <tr>
                        <th className="px-6 py-4 font-medium tracking-wider">Directory Name</th>
                        <th className="px-6 py-4 font-medium tracking-wider">Status</th>
                        <th className="px-6 py-4 font-medium tracking-wider text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {installed.map((name) => (
                        <tr key={name} className="hover:bg-white/[0.02] transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 rounded bg-white/10 flex items-center justify-center flex-shrink-0">
                                <Package className="w-4 h-4 text-zinc-400" />
                              </div>
                              <span className="font-medium text-zinc-200">{name}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">
                              <span className="w-1.5 h-1.5 rounded-full bg-green-500"></span> Installed
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <button
                              onClick={() => uninstallAddon(name)}
                              disabled={uninstallingName === name}
                              className="text-zinc-500 hover:text-red-400 transition-colors text-xs font-medium px-2 py-1 rounded hover:bg-red-400/10 disabled:opacity-50"
                            >
                              {uninstallingName === name ? 'Removing...' : 'Uninstall'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </motion.div>
          )}

          {view === 'settings' && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="max-w-2xl mx-auto">
              <h2 className="text-3xl font-bold tracking-tight text-zinc-100 mb-8">Settings</h2>

              <div className="space-y-6">
                <div className="bg-[#0c0c10] border border-white/10 rounded-2xl p-6 shadow-xl">
                  <h3 className="text-lg font-medium text-zinc-200 mb-4">Installation Directory</h3>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-zinc-400">ESO AddOns Path</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        readOnly
                        value="~\Documents\Elder Scrolls Online\live\AddOns"
                        className="flex-1 bg-zinc-900 border border-white/10 rounded-lg py-2 px-3 text-sm text-zinc-400 focus:outline-none focus:border-blue-500/50"
                      />
                      <button className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 transition-colors text-sm font-medium text-zinc-200 border border-white/5">
                        Browse
                      </button>
                    </div>
                    <p className="text-xs text-zinc-500 mt-2">This is where your Addons will be installed natively.</p>
                  </div>
                </div>

                <div className="bg-[#0c0c10] border border-white/10 rounded-2xl p-6 shadow-xl">
                  <h3 className="text-lg font-medium text-zinc-200 mb-4">App Preferences</h3>
                  <div className="flex items-center justify-between py-3">
                    <div>
                      <h4 className="text-sm font-medium text-zinc-300">Backups</h4>
                      <p className="text-xs text-zinc-500 mt-0.5">Create a backup of SavedVariables before updating.</p>
                    </div>
                    <div className="w-10 h-6 bg-zinc-800 border border-white/5 rounded-full cursor-pointer relative shadow-inner">
                      <div className="absolute left-1 top-1 w-4 h-4 bg-zinc-400 rounded-full shadow-sm"></div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

        </div>
      </main>

      {/* Modal / Dialog for Addon Details */}
      <AnimatePresence>
        {selectedAddon && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-sm"
            onClick={() => setSelectedAddon(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              transition={{ type: "spring", damping: 25, stiffness: 300 }}
              className="bg-[#0c0c10] border border-white/10 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
              onClick={e => e.stopPropagation()}
            >
              <div className="px-6 py-5 border-b border-white/5 flex justify-between items-start shrink-0 bg-white/[0.01]">
                <div>
                  <h2 className="text-2xl font-bold text-zinc-100 flex items-center gap-3">
                    <span dangerouslySetInnerHTML={{ __html: selectedAddon.name }} />
                    {selectedAddon.is_installed && (
                       <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">Installed</span>
                    )}
                  </h2>
                  <div className="flex items-center gap-4 mt-2 text-sm text-zinc-400">
                    <span>by <strong className="text-zinc-200">{selectedAddon.author_name}</strong></span>
                    <span className="w-1 h-1 rounded-full bg-zinc-700"></span>
                    <span>Version {selectedAddon.version}</span>
                    <span className="w-1 h-1 rounded-full bg-zinc-700"></span>
                    <span className="flex items-center gap-1"><Download className="w-3.5 h-3.5" /> {(selectedAddon.download_total / 1000).toFixed(1)}k</span>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedAddon(null)}
                  className="p-1.5 rounded-md hover:bg-white/10 text-zinc-400 hover:text-white transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 text-zinc-300 text-sm leading-relaxed prose prose-invert max-w-none custom-scroll" style={{ whiteSpace: 'pre-line' }}>
                <span dangerouslySetInnerHTML={{ __html: parseBBCode(selectedAddon.description) }} />
              </div>

              <div className="px-6 py-4 border-t border-white/5 bg-zinc-900/50 shrink-0 flex justify-between items-center">
                <span className="text-xs text-zinc-500">Addon ID: {selectedAddon.id}</span>

                {selectedAddon.is_installed ? (
                  <button
                    onClick={() => {
                      const dirs = selectedAddon.directories ? selectedAddon.directories.split(',') : [];
                      const matchedDir = dirs.find(d => installed.includes(d));
                      if (matchedDir) {
                        uninstallAddon(matchedDir);
                      } else {
                        alert('Could not determine addon directory. Please uninstall from My Addons tab.');
                      }
                    }}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium text-sm bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all border border-red-500/20"
                  >
                    <Trash2 className="w-4 h-4" /> Uninstall
                  </button>
                ) : (
                  <button
                    disabled={installingId === selectedAddon.id}
                    onClick={() => installAddon(selectedAddon.id, selectedAddon.name)}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium text-sm bg-blue-600 hover:bg-blue-500 text-white transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50"
                  >
                    {installingId === selectedAddon.id ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" /> Installing...
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4" /> Install Now
                      </>
                    )}
                  </button>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
}

export default App;
```

Key changes:
- Added `uninstallAddon()` function with confirmation dialog
- Wired up Uninstall button in My Addons tab (was non-functional)
- Added Uninstall (trash icon) button next to "Installed" badge in Discover tab
- Detail modal: "Already Installed" button replaced with "Uninstall" button
- Added update banner at top of main content area
- Removed "Update All" button (not implemented)
- Removed "Auto-update Addons on Launch" toggle (not implemented)
- Added `Trash2` icon import from lucide-react
- Added `uninstallingName` state for loading indicator

- [ ] **Step 2: Verify frontend builds**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager/frontend
npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
git add frontend/src/App.tsx
git commit -m "feat: add uninstall buttons, update banner, remove dead UI"
```

---

## Chunk 5: Build Fix + GitHub Actions + Cleanup (Tasks 7-9)

### Task 7: Fix PyInstaller Build

**Files:**
- Modify: `ESO_Power_Lite.spec`

- [ ] **Step 1: Update ESO_Power_Lite.spec with hidden imports**

Replace the entire contents of `ESO_Power_Lite.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('frontend/dist', 'frontend/dist')],
    hiddenimports=[
        'webview',
        'clr_loader',
        'pythonnet',
        'bottle',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ESO_Power_Lite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ESO_Power_Lite',
)
```

- [ ] **Step 2: Install pywebview if not already installed**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
pip install pywebview
```

- [ ] **Step 3: Test the build**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager/frontend && npm run build && cd .. && pyinstaller --noconfirm ESO_Power_Lite.spec
```

Expected: Build completes. `dist/ESO_Power_Lite/ESO_Power_Lite.exe` is created.

- [ ] **Step 4: Commit**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
git add ESO_Power_Lite.spec requirements.txt
git commit -m "fix: add pywebview hidden imports to PyInstaller spec"
```

---

### Task 8: Create GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/sync-addons.yml`

- [ ] **Step 1: Create workflow directory**

```bash
mkdir -p C:/Users/User/Documents/Hobby/eso-addon-manager/.github/workflows
```

- [ ] **Step 2: Create sync-addons.yml**

Create `.github/workflows/sync-addons.yml`:

```yaml
name: Sync Addon Database

on:
  schedule:
    # Runs twice daily at 6am and 6pm UTC
    - cron: '0 6,18 * * *'
  workflow_dispatch:  # Allow manual trigger

jobs:
  sync:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests

      - name: Run sync script
        run: python scripts/sync_to_sqlite.py addons.db

      - name: Get database stats
        run: |
          python -c "
          import sqlite3
          conn = sqlite3.connect('addons.db')
          addons = conn.execute('SELECT COUNT(*) FROM addons').fetchone()[0]
          cats = conn.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
          synced = conn.execute(\"SELECT value FROM metadata WHERE key='last_synced'\").fetchone()[0]
          print(f'Addons: {addons}, Categories: {cats}, Synced: {synced}')
          conn.close()
          "

      - name: Delete old release asset
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # Get the release
          RELEASE=$(gh api repos/${{ github.repository }}/releases/tags/data-latest 2>/dev/null || echo "")
          if [ -n "$RELEASE" ]; then
            # Delete existing addons.db asset if present
            ASSET_ID=$(echo "$RELEASE" | jq -r '.assets[] | select(.name == "addons.db") | .id' 2>/dev/null || echo "")
            if [ -n "$ASSET_ID" ]; then
              gh api -X DELETE repos/${{ github.repository }}/releases/assets/$ASSET_ID
              echo "Deleted old addons.db asset"
            fi
          else
            # Create the release if it doesn't exist
            gh release create data-latest --title "Addon Database (Auto-Updated)" --notes "This release contains the automatically synced addon database. Updated twice daily." --latest=false
            echo "Created data-latest release"
          fi

      - name: Upload new database
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release upload data-latest addons.db --clobber
          echo "Uploaded new addons.db"
```

- [ ] **Step 3: Commit**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
git add .github/workflows/sync-addons.yml
git commit -m "feat: add GitHub Actions workflow for addon database sync"
```

---

### Task 9: Delete backend/db.py + Final Cleanup

**Files:**
- Delete: `backend/db.py`

- [ ] **Step 1: Delete backend/db.py**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
rm backend/db.py
```

This file contained hardcoded Neon PostgreSQL credentials and is fully replaced by `scripts/sync_to_sqlite.py`.

- [ ] **Step 2: Verify nothing imports db.py**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
grep -r "from backend.db\|import db\|backend/db" --include="*.py" .
```

Expected: No matches (nothing references `backend/db.py`).

- [ ] **Step 3: Verify the full app starts**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
python main.py
```

Expected: App launches (may show "GITHUB_OWNER not configured" message, which is expected until the user creates their GitHub repo). The webview window should open. If no `addons.db` exists locally, addon list will be empty.

- [ ] **Step 4: Commit**

```bash
cd C:/Users/User/Documents/Hobby/eso-addon-manager
git add -A
git commit -m "chore: remove deprecated PostgreSQL sync script with hardcoded credentials"
```

- [ ] **Step 5: Reminder — rotate Neon credentials**

After this migration is complete, the user should:
1. Log into Neon dashboard
2. Rotate or delete the database password that was hardcoded
3. Consider deprovisioning the Neon database entirely if no longer needed
