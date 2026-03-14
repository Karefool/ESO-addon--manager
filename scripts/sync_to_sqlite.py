"""
Sync MMOUI addon data to a local SQLite database.
Run by GitHub Actions on a schedule, or locally for testing.
Performs incremental updates: only fetches descriptions for new/changed addons.
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

    # Get existing category IDs
    cursor.execute("SELECT id FROM categories")
    existing_ids = {row[0] for row in cursor.fetchall()}
    remote_ids = set()

    for cat in categories:
        cat_id = cat.get('UICATID')
        remote_ids.add(cat_id)
        parent_ids = cat.get('UICATParentIDs', '')
        if isinstance(parent_ids, list):
            parent_ids = ",".join(parent_ids)

        cursor.execute('''
            INSERT OR REPLACE INTO categories (id, title, icon, file_count, parent_ids)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            cat_id,
            cat.get('UICATTitle'),
            cat.get('UICATICON'),
            int(cat.get('UICATFileCount', 0)),
            str(parent_ids)
        ))

    # Remove categories that no longer exist on MMOUI
    removed = existing_ids - remote_ids
    if removed:
        cursor.executemany("DELETE FROM categories WHERE id = ?", [(cid,) for cid in removed])
        print(f"  Removed {len(removed)} defunct categories.")

    conn.commit()
    print(f"Synced {len(categories)} categories.")


def sync_addons(conn, api):
    print("Fetching addon list...")
    addons = api.fetch_addons()
    cursor = conn.cursor()

    # Build a map of existing addons: id -> (version, last_updated)
    cursor.execute("SELECT id, version, last_updated FROM addons")
    existing = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    remote_ids = set()

    new_count = 0
    updated_count = 0
    unchanged_count = 0
    needs_description = []

    print(f"Processing {len(addons)} addons...")
    for addon in addons:
        addon_id = addon.get('UID')
        remote_ids.add(addon_id)

        dl_total = str(addon.get('UIDownloadTotal', '0')).replace(',', '')
        dl_monthly = str(addon.get('UIDownloadMonthly', '0')).replace(',', '')
        fav_total = str(addon.get('UIFavoriteTotal', '0')).replace(',', '')

        directories = addon.get('UIDir', [])
        if isinstance(directories, list):
            directories = ",".join(directories)

        new_version = addon.get('UIVersion')
        new_last_updated = int(addon.get('UIDate', 0))

        if addon_id in existing:
            old_version, old_last_updated = existing[addon_id]
            if old_version == new_version and old_last_updated == new_last_updated:
                # Only update download counts (change frequently but don't need description refetch)
                cursor.execute('''
                    UPDATE addons SET download_total = ?, download_monthly = ?, favorite_total = ?
                    WHERE id = ?
                ''', (
                    int(dl_total) if dl_total.isdigit() else 0,
                    int(dl_monthly) if dl_monthly.isdigit() else 0,
                    int(fav_total) if fav_total.isdigit() else 0,
                    addon_id
                ))
                unchanged_count += 1
            else:
                # Version or date changed — update metadata and refetch description
                cursor.execute('''
                    UPDATE addons SET category_id = ?, version = ?, last_updated = ?,
                        name = ?, author_name = ?, file_info_url = ?,
                        download_total = ?, download_monthly = ?, favorite_total = ?,
                        directories = ?, description = NULL
                    WHERE id = ?
                ''', (
                    addon.get('UICATID'), new_version, new_last_updated,
                    addon.get('UIName'), addon.get('UIAuthorName'),
                    addon.get('UIFileInfoURL'),
                    int(dl_total) if dl_total.isdigit() else 0,
                    int(dl_monthly) if dl_monthly.isdigit() else 0,
                    int(fav_total) if fav_total.isdigit() else 0,
                    directories, addon_id
                ))
                needs_description.append(addon_id)
                updated_count += 1
        else:
            # New addon — insert and queue for description fetch
            cursor.execute('''
                INSERT INTO addons
                (id, category_id, version, last_updated, name, author_name,
                 file_info_url, download_total, download_monthly, favorite_total, directories)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                addon_id, addon.get('UICATID'), new_version, new_last_updated,
                addon.get('UIName'), addon.get('UIAuthorName'),
                addon.get('UIFileInfoURL'),
                int(dl_total) if dl_total.isdigit() else 0,
                int(dl_monthly) if dl_monthly.isdigit() else 0,
                int(fav_total) if fav_total.isdigit() else 0,
                directories
            ))
            needs_description.append(addon_id)
            new_count += 1

    # Remove addons that no longer exist on MMOUI
    removed_ids = set(existing.keys()) - remote_ids
    if removed_ids:
        cursor.executemany("DELETE FROM addons WHERE id = ?", [(aid,) for aid in removed_ids])

    conn.commit()
    print(f"  New: {new_count}, Updated: {updated_count}, Unchanged: {unchanged_count}, Removed: {len(removed_ids)}")

    # Also include any existing addons that still have no description
    cursor.execute("SELECT id FROM addons WHERE description IS NULL OR description = ''")
    existing_missing = {row[0] for row in cursor.fetchall()}
    # Merge: new/updated addons + any that were missing descriptions from before
    all_needing_desc = list(set(needs_description) | existing_missing)

    if not all_needing_desc:
        print("All addons already have descriptions. Nothing to fetch.")
        return

    print(f"Fetching descriptions for {len(all_needing_desc)} addons...")
    fetched = 0
    errors = 0
    consecutive_errors = 0

    for addon_id in all_needing_desc:
        try:
            details = api.fetch_addon_details(addon_id)
            description = details.get('UIDescription', '') if details else ''
            cursor.execute(
                'UPDATE addons SET description = ? WHERE id = ?',
                (description, addon_id)
            )
            fetched += 1
            consecutive_errors = 0
            if fetched % 100 == 0:
                conn.commit()
                print(f"  Fetched {fetched}/{len(all_needing_desc)} descriptions...")
            # Rate limit: 0.5s between requests
            time.sleep(0.5)
        except Exception as e:
            errors += 1
            consecutive_errors += 1
            if errors <= 10:
                print(f"  Warning: failed to fetch description for {addon_id}: {e}")
            if consecutive_errors >= 20:
                print(f"  Too many consecutive errors ({consecutive_errors}). Stopping description fetch.")
                break

    conn.commit()
    print(f"Descriptions done. Fetched: {fetched}, Errors: {errors}")


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

    print(f"Opening database at {output_path}")
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
