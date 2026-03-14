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
            where_clauses.append("(name LIKE ? OR author_name LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

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

        # Fetch paginated - prioritize name matches when searching
        offset = (page - 1) * limit
        if query:
            order_clause = f"CASE WHEN name LIKE ? THEN 0 ELSE 1 END, {sort_by} {'ASC' if order == 'asc' else 'DESC'}"
            sql = f"""
                SELECT * FROM addons
                {where_stmt}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
            """
            params.extend([f"%{query}%", limit, offset])
        else:
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
