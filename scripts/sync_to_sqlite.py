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
