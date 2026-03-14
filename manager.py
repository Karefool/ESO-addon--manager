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
