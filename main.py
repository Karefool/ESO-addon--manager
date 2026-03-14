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
