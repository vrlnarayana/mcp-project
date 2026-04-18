import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "jobs.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(seed: bool = True) -> None:
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            title            TEXT NOT NULL,
            company          TEXT NOT NULL,
            location         TEXT NOT NULL,
            skills           TEXT NOT NULL,
            job_type         TEXT NOT NULL,
            experience_level TEXT NOT NULL,
            salary_min       INTEGER NOT NULL,
            salary_max       INTEGER NOT NULL,
            description      TEXT NOT NULL,
            posted_at        TEXT NOT NULL,
            is_open          INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()
    if seed:
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if count == 0:
            from seed_data import JOBS
            conn.executemany(
                """INSERT INTO jobs (title,company,location,skills,job_type,experience_level,
                   salary_min,salary_max,description,posted_at,is_open)
                   VALUES (:title,:company,:location,:skills,:job_type,:experience_level,
                           :salary_min,:salary_max,:description,:posted_at,:is_open)""",
                JOBS,
            )
            conn.commit()
    conn.close()


def db_list_jobs(
    page: int = 1,
    page_size: int = 10,
    location: Optional[str] = None,
    job_type: Optional[str] = None,
    experience_level: Optional[str] = None,
) -> dict:
    conn = get_connection()
    conditions = ["is_open = 1"]
    params: list = []
    if location:
        conditions.append("LOWER(location) LIKE ?")
        params.append(f"%{location.lower()}%")
    if job_type:
        conditions.append("LOWER(job_type) = ?")
        params.append(job_type.lower())
    if experience_level:
        conditions.append("LOWER(experience_level) = ?")
        params.append(experience_level.lower())

    where = " AND ".join(conditions)
    total = conn.execute(f"SELECT COUNT(*) FROM jobs WHERE {where}", params).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM jobs WHERE {where} LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    conn.close()
    return {"jobs": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


def db_get_job(job_id: int) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return {"error": f"Job {job_id} not found"}
    return dict(row)


def db_search_jobs(
    query: str,
    location: Optional[str] = None,
    skill: Optional[str] = None,
) -> list:
    conn = get_connection()
    q = f"%{query.lower()}%"
    conditions = [
        "is_open = 1",
        "(LOWER(title) LIKE ? OR LOWER(skills) LIKE ? OR LOWER(description) LIKE ?)",
    ]
    params: list = [q, q, q]
    if location:
        conditions.append("LOWER(location) LIKE ?")
        params.append(f"%{location.lower()}%")
    if skill:
        conditions.append("LOWER(skills) LIKE ?")
        params.append(f"%{skill.lower()}%")
    where = " AND ".join(conditions)
    rows = conn.execute(f"SELECT * FROM jobs WHERE {where} LIMIT 20", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
