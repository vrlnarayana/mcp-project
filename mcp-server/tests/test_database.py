import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import database


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.init_db(seed=False)
    yield
    conn = database.get_connection()
    conn.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def _insert_job(conn, overrides=None):
    job = {
        "title": "React Developer",
        "company": "Acme",
        "location": "Bangalore",
        "skills": "React, TypeScript",
        "job_type": "full-time",
        "experience_level": "mid",
        "salary_min": 1000000,
        "salary_max": 1500000,
        "description": "Build UIs.",
        "posted_at": "2026-01-01",
        "is_open": 1,
    }
    if overrides:
        job.update(overrides)
    conn.execute(
        """INSERT INTO jobs (title,company,location,skills,job_type,experience_level,
           salary_min,salary_max,description,posted_at,is_open)
           VALUES (:title,:company,:location,:skills,:job_type,:experience_level,
                   :salary_min,:salary_max,:description,:posted_at,:is_open)""",
        job,
    )
    conn.commit()


def test_init_db_creates_table(db):
    conn = database.get_connection()
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'").fetchall()
    conn.close()
    assert len(rows) == 1


def test_list_jobs_returns_paginated(db):
    conn = database.get_connection()
    for i in range(15):
        _insert_job(conn, {"title": f"Job {i}"})
    conn.close()

    result = database.db_list_jobs(page=1, page_size=10)
    assert len(result["jobs"]) == 10
    assert result["total"] == 15
    assert result["page"] == 1


def test_list_jobs_filters_by_location(db):
    conn = database.get_connection()
    _insert_job(conn, {"location": "Chennai"})
    _insert_job(conn, {"location": "Mumbai"})
    conn.close()

    result = database.db_list_jobs(location="Chennai")
    assert all(j["location"] == "Chennai" for j in result["jobs"])
    assert result["total"] == 1


def test_list_jobs_filters_by_job_type(db):
    conn = database.get_connection()
    _insert_job(conn, {"job_type": "remote"})
    _insert_job(conn, {"job_type": "full-time"})
    conn.close()

    result = database.db_list_jobs(job_type="remote")
    assert result["total"] == 1
    assert result["jobs"][0]["job_type"] == "remote"


def test_list_jobs_filters_by_experience_level(db):
    conn = database.get_connection()
    _insert_job(conn, {"experience_level": "senior"})
    _insert_job(conn, {"experience_level": "junior"})
    conn.close()

    result = database.db_list_jobs(experience_level="senior")
    assert result["total"] == 1


def test_list_jobs_excludes_closed(db):
    conn = database.get_connection()
    _insert_job(conn, {"is_open": 0})
    _insert_job(conn, {"is_open": 1})
    conn.close()

    result = database.db_list_jobs()
    assert result["total"] == 1


def test_get_job_returns_record(db):
    conn = database.get_connection()
    _insert_job(conn)
    job_id = conn.execute("SELECT id FROM jobs LIMIT 1").fetchone()[0]
    conn.close()

    result = database.db_get_job(job_id)
    assert result["title"] == "React Developer"
    assert result["company"] == "Acme"


def test_get_job_returns_error_for_missing(db):
    result = database.db_get_job(9999)
    assert "error" in result


def test_search_jobs_matches_title(db):
    conn = database.get_connection()
    _insert_job(conn, {"title": "Python Engineer"})
    _insert_job(conn, {"title": "Java Developer"})
    conn.close()

    results = database.db_search_jobs("Python")
    assert len(results) == 1
    assert results[0]["title"] == "Python Engineer"


def test_search_jobs_matches_skills(db):
    conn = database.get_connection()
    _insert_job(conn, {"skills": "React, Redux, TypeScript"})
    _insert_job(conn, {"skills": "Django, PostgreSQL"})
    conn.close()

    results = database.db_search_jobs("Redux")
    assert len(results) == 1


def test_search_jobs_filters_location(db):
    conn = database.get_connection()
    _insert_job(conn, {"title": "React Dev", "location": "Bangalore"})
    _insert_job(conn, {"title": "React Dev", "location": "Chennai"})
    conn.close()

    results = database.db_search_jobs("React", location="Bangalore")
    assert len(results) == 1
    assert results[0]["location"] == "Bangalore"


def test_search_jobs_filters_skill(db):
    conn = database.get_connection()
    _insert_job(conn, {"skills": "React, TypeScript"})
    _insert_job(conn, {"skills": "Vue, JavaScript"})
    conn.close()

    results = database.db_search_jobs("React", skill="TypeScript")
    assert len(results) == 1
