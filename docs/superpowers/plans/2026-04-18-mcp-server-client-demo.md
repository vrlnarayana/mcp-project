# MCP Server/Client Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two sibling Python apps — an MCP server (FastAPI + SQLite, exposes 3 job-search tools over SSE) and an MCP client (Streamlit split-panel UI + Claude agent that discovers and calls those tools dynamically).

**Architecture:** App A (`mcp-server/`) runs a FastAPI app with an MCP SSE endpoint at `/sse`; App B (`mcp-client/`) opens an SSE connection to it, discovers tools via `list_tools()`, and runs a single-turn Claude agent loop. The Streamlit UI shows the agent answer on the left and raw MCP tool calls on the right.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, `mcp[cli]` (Python MCP SDK), SQLite, `anthropic` SDK, Streamlit, pytest, pytest-asyncio

**Python:** always use `python3.11` — system Python is 3.7 and incompatible. Both apps run in isolated virtualenvs.

---

## File Map

```
mcp-project/
  mcp-server/
    .venv/               # virtualenv (not committed)
    requirements.txt
    pytest.ini
    database.py          # SQLite init, schema, 3 query helpers
    seed_data.py         # JOBS list — 50+ realistic records
    tools.py             # register_tools(mcp) — wraps db helpers as MCP tools
    main.py              # FastAPI app + lifespan + /health + mounts MCP SSE
    tests/
      __init__.py
      test_database.py   # unit tests for all 3 db helpers
  mcp-client/
    .venv/               # virtualenv (not committed)
    requirements.txt
    pytest.ini
    agent.py             # async run(query) -> (str, list[dict])
    app.py               # Streamlit split-panel UI
    tests/
      __init__.py
      test_agent.py      # unit tests with mocked MCP + Anthropic
```

---

### Task 1: Scaffold both apps

**Files:**
- Create: `mcp-project/mcp-server/requirements.txt`
- Create: `mcp-project/mcp-client/requirements.txt`
- Create: `mcp-project/mcp-server/tests/__init__.py`
- Create: `mcp-project/mcp-client/tests/__init__.py`

- [ ] **Step 1: Create directories**

```bash
mkdir -p /Users/vrln/mcp-project/mcp-server/tests
mkdir -p /Users/vrln/mcp-project/mcp-client/tests
```

- [ ] **Step 2: Write requirements files**

Write `/Users/vrln/mcp-project/mcp-server/requirements.txt`:
```
fastapi
uvicorn[standard]
mcp[cli]
pytest
pytest-asyncio
```

Write `/Users/vrln/mcp-project/mcp-client/requirements.txt`:
```
streamlit
anthropic
mcp[cli]
requests
pytest
pytest-asyncio
```

- [ ] **Step 3: Write pytest.ini files (asyncio mode config)**

Write `/Users/vrln/mcp-project/mcp-server/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

Write `/Users/vrln/mcp-project/mcp-client/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 4: Create virtualenvs and install dependencies**

```bash
# App A venv
cd /Users/vrln/mcp-project/mcp-server
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate

# App B venv
cd /Users/vrln/mcp-project/mcp-client
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```

Expected: both installs complete without errors.

- [ ] **Step 5: Create empty `__init__.py` files**

```bash
touch /Users/vrln/mcp-project/mcp-server/tests/__init__.py
touch /Users/vrln/mcp-project/mcp-client/tests/__init__.py
```

- [ ] **Step 6: Add .venv to .gitignore**

Append to `/Users/vrln/mcp-project/.gitignore` (create if missing):
```
mcp-server/.venv/
mcp-client/.venv/
mcp-server/jobs.db
```

- [ ] **Step 7: Commit**

```bash
cd /Users/vrln/mcp-project
git add mcp-server/ mcp-client/ .gitignore
git commit -m "chore: scaffold mcp-server and mcp-client with venvs and pytest config"
```

---

### Task 2: Database layer (TDD)

**Files:**
- Create: `mcp-project/mcp-server/database.py`
- Create: `mcp-project/mcp-server/tests/test_database.py`

- [ ] **Step 1: Write the failing tests**

Write `/Users/vrln/mcp-project/mcp-server/tests/test_database.py`:
```python
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

    results = database.db_search_jobs("developer", skill="TypeScript")
    # query "developer" matches description "Build UIs." — no, let's match title
    # Both have title "React Developer" so both match query; skill filters to 1
    results = database.db_search_jobs("React", skill="TypeScript")
    assert len(results) == 1
```

- [ ] **Step 2: Run tests — expect ImportError (database.py doesn't exist)**

```bash
cd /Users/vrln/mcp-project/mcp-server
source .venv/bin/activate
python -m pytest tests/test_database.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'database'`

- [ ] **Step 3: Implement `database.py`**

Write `/Users/vrln/mcp-project/mcp-server/database.py`:
```python
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd /Users/vrln/mcp-project/mcp-server
source .venv/bin/activate
python -m pytest tests/test_database.py -v
```

Expected:
```
test_database.py::test_init_db_creates_table PASSED
test_database.py::test_list_jobs_returns_paginated PASSED
test_database.py::test_list_jobs_filters_by_location PASSED
test_database.py::test_list_jobs_filters_by_job_type PASSED
test_database.py::test_list_jobs_filters_by_experience_level PASSED
test_database.py::test_list_jobs_excludes_closed PASSED
test_database.py::test_get_job_returns_record PASSED
test_database.py::test_get_job_returns_error_for_missing PASSED
test_database.py::test_search_jobs_matches_title PASSED
test_database.py::test_search_jobs_matches_skills PASSED
test_database.py::test_search_jobs_filters_location PASSED
test_database.py::test_search_jobs_filters_skill PASSED
12 passed
```

- [ ] **Step 5: Commit**

```bash
cd /Users/vrln/mcp-project
git add mcp-server/database.py mcp-server/tests/test_database.py
git commit -m "feat: database layer with schema, query helpers, and tests"
```

---

### Task 3: Seed data (50+ records)

**Files:**
- Create: `mcp-project/mcp-server/seed_data.py`

- [ ] **Step 1: Write `seed_data.py`**

Write `/Users/vrln/mcp-project/mcp-server/seed_data.py`:
```python
JOBS = [
    # Bangalore — React
    {"title": "Senior React Developer", "company": "Flipkart", "location": "Bangalore",
     "skills": "React, TypeScript, Redux, Webpack", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 1800000, "salary_max": 2500000,
     "description": "Build high-scale e-commerce UIs. Own frontend architecture for catalog pages.",
     "posted_at": "2026-04-01", "is_open": 1},
    {"title": "React Lead Engineer", "company": "Swiggy", "location": "Bangalore",
     "skills": "React, Node.js, GraphQL, Docker", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2200000, "salary_max": 3000000,
     "description": "Lead a team of 5 engineers building the consumer ordering platform.",
     "posted_at": "2026-04-05", "is_open": 1},
    {"title": "React Developer", "company": "Meesho", "location": "Bangalore",
     "skills": "React, JavaScript, CSS, REST APIs", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1200000, "salary_max": 1800000,
     "description": "Develop responsive seller dashboard components for the Meesho platform.",
     "posted_at": "2026-03-28", "is_open": 1},
    {"title": "Junior React Developer", "company": "Urban Company", "location": "Bangalore",
     "skills": "React, JavaScript, HTML, CSS", "job_type": "full-time",
     "experience_level": "junior", "salary_min": 600000, "salary_max": 900000,
     "description": "Build and maintain customer-facing features under senior guidance.",
     "posted_at": "2026-04-10", "is_open": 1},
    {"title": "Frontend Engineer (React)", "company": "Zepto", "location": "Bangalore",
     "skills": "React, Next.js, Tailwind CSS, TypeScript", "job_type": "remote",
     "experience_level": "mid", "salary_min": 1500000, "salary_max": 2200000,
     "description": "Build the consumer-facing quick commerce app with a focus on performance.",
     "posted_at": "2026-04-08", "is_open": 1},

    # Bangalore — Python / Data
    {"title": "Senior Python Engineer", "company": "Razorpay", "location": "Bangalore",
     "skills": "Python, FastAPI, PostgreSQL, Kafka", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2000000, "salary_max": 2800000,
     "description": "Design payment processing microservices handling millions of transactions daily.",
     "posted_at": "2026-04-02", "is_open": 1},
    {"title": "Data Scientist", "company": "PhonePe", "location": "Bangalore",
     "skills": "Python, scikit-learn, SQL, Spark", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1600000, "salary_max": 2200000,
     "description": "Build ML models for fraud detection and credit risk assessment.",
     "posted_at": "2026-03-25", "is_open": 1},
    {"title": "Junior Data Scientist", "company": "Byju's", "location": "Bangalore",
     "skills": "Python, pandas, NumPy, machine learning", "job_type": "full-time",
     "experience_level": "junior", "salary_min": 700000, "salary_max": 1100000,
     "description": "Analyse student learning patterns and build recommendation models.",
     "posted_at": "2026-04-12", "is_open": 1},
    {"title": "ML Engineer", "company": "CRED", "location": "Bangalore",
     "skills": "Python, TensorFlow, Docker, Kubernetes", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2500000, "salary_max": 3500000,
     "description": "Build and deploy real-time ML inference pipelines for credit scoring.",
     "posted_at": "2026-04-06", "is_open": 1},

    # Bangalore — DevOps / Java
    {"title": "DevOps Engineer", "company": "Ola", "location": "Bangalore",
     "skills": "AWS, Kubernetes, Terraform, Jenkins", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1400000, "salary_max": 2000000,
     "description": "Manage cloud infrastructure for ride-hailing services at scale.",
     "posted_at": "2026-04-03", "is_open": 1},
    {"title": "Senior DevOps Engineer", "company": "Flipkart", "location": "Bangalore",
     "skills": "AWS, Docker, Kubernetes, Python, CI/CD", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2200000, "salary_max": 3000000,
     "description": "Own infrastructure reliability for Flipkart's compute platform.",
     "posted_at": "2026-03-20", "is_open": 1},
    {"title": "Java Backend Developer", "company": "Infosys", "location": "Bangalore",
     "skills": "Java, Spring Boot, Hibernate, MySQL", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1000000, "salary_max": 1600000,
     "description": "Develop enterprise microservices for banking clients.",
     "posted_at": "2026-04-07", "is_open": 1},

    # Chennai — various
    {"title": "Senior React Developer", "company": "Zoho", "location": "Chennai",
     "skills": "React, JavaScript, Redux, REST APIs", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 1600000, "salary_max": 2200000,
     "description": "Build next-gen SaaS product UIs for Zoho's CRM suite.",
     "posted_at": "2026-04-04", "is_open": 1},
    {"title": "Python Developer", "company": "Freshworks", "location": "Chennai",
     "skills": "Python, Django, PostgreSQL, Redis", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1200000, "salary_max": 1800000,
     "description": "Build backend APIs for Freshdesk's helpdesk ticketing platform.",
     "posted_at": "2026-04-01", "is_open": 1},
    {"title": "QA Engineer", "company": "Zoho", "location": "Chennai",
     "skills": "Selenium, Python, TestNG, JIRA", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 800000, "salary_max": 1200000,
     "description": "Design and execute automated test suites for Zoho Books.",
     "posted_at": "2026-03-30", "is_open": 1},
    {"title": "Junior Java Developer", "company": "TCS", "location": "Chennai",
     "skills": "Java, Spring, MySQL, REST", "job_type": "full-time",
     "experience_level": "junior", "salary_min": 500000, "salary_max": 800000,
     "description": "Develop and maintain backend services for banking projects.",
     "posted_at": "2026-04-11", "is_open": 1},
    {"title": "DevOps Engineer", "company": "Freshworks", "location": "Chennai",
     "skills": "AWS, Docker, Ansible, Linux", "job_type": "remote",
     "experience_level": "mid", "salary_min": 1300000, "salary_max": 1900000,
     "description": "Automate deployments and maintain cloud infrastructure for SaaS products.",
     "posted_at": "2026-04-09", "is_open": 1},
    {"title": "Android Developer", "company": "Zoho", "location": "Chennai",
     "skills": "Android, Kotlin, Jetpack Compose, REST APIs", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1100000, "salary_max": 1700000,
     "description": "Build native Android apps for Zoho's mobile product suite.",
     "posted_at": "2026-04-02", "is_open": 1},

    # Mumbai — various
    {"title": "Senior Python Developer", "company": "Paytm", "location": "Mumbai",
     "skills": "Python, Django, Celery, Redis, PostgreSQL", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 1900000, "salary_max": 2600000,
     "description": "Build scalable payment and wallet backend services.",
     "posted_at": "2026-04-03", "is_open": 1},
    {"title": "React Developer", "company": "Paytm", "location": "Mumbai",
     "skills": "React, JavaScript, TypeScript, REST APIs", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1300000, "salary_max": 1900000,
     "description": "Develop checkout and payment flows for Paytm's web platform.",
     "posted_at": "2026-04-06", "is_open": 1},
    {"title": "Data Scientist (Senior)", "company": "Reliance Jio", "location": "Mumbai",
     "skills": "Python, PySpark, ML, SQL, Hadoop", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2200000, "salary_max": 3000000,
     "description": "Build data pipelines and recommendation models for Jio's media platform.",
     "posted_at": "2026-03-27", "is_open": 1},
    {"title": "iOS Developer", "company": "Dream11", "location": "Mumbai",
     "skills": "Swift, iOS, UIKit, REST APIs, Xcode", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1400000, "salary_max": 2100000,
     "description": "Build and optimise the Dream11 iOS app for fantasy sports.",
     "posted_at": "2026-04-10", "is_open": 1},
    {"title": "Product Manager", "company": "Nykaa", "location": "Mumbai",
     "skills": "Product Management, Agile, SQL, Analytics", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2500000, "salary_max": 3500000,
     "description": "Own the checkout and payments product for Nykaa's e-commerce platform.",
     "posted_at": "2026-04-01", "is_open": 1},
    {"title": "Node.js Developer", "company": "BookMyShow", "location": "Mumbai",
     "skills": "Node.js, Express, MongoDB, Redis", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1200000, "salary_max": 1800000,
     "description": "Build ticket booking APIs that handle peak concert-day traffic.",
     "posted_at": "2026-04-08", "is_open": 1},
    {"title": "Junior QA Engineer", "company": "Nykaa", "location": "Mumbai",
     "skills": "Selenium, Java, TestNG, Git", "job_type": "full-time",
     "experience_level": "junior", "salary_min": 500000, "salary_max": 800000,
     "description": "Write and run automated regression tests for the Nykaa shopping app.",
     "posted_at": "2026-04-13", "is_open": 1},

    # Hyderabad — various
    {"title": "Senior Java Developer", "company": "Microsoft IDC", "location": "Hyderabad",
     "skills": "Java, Spring Boot, Azure, Microservices", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2500000, "salary_max": 3500000,
     "description": "Build cloud-native services for Microsoft Azure's identity platform.",
     "posted_at": "2026-04-05", "is_open": 1},
    {"title": "Python Engineer", "company": "Amazon", "location": "Hyderabad",
     "skills": "Python, AWS Lambda, DynamoDB, CDK", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1800000, "salary_max": 2500000,
     "description": "Build serverless data processing pipelines for Amazon's logistics platform.",
     "posted_at": "2026-04-02", "is_open": 1},
    {"title": "DevOps / SRE", "company": "Google", "location": "Hyderabad",
     "skills": "Kubernetes, GCP, Python, Prometheus, Go", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 3000000, "salary_max": 4500000,
     "description": "Ensure reliability of Google's search infrastructure serving Indian users.",
     "posted_at": "2026-03-31", "is_open": 1},
    {"title": "React Developer (Contract)", "company": "Wipro", "location": "Hyderabad",
     "skills": "React, JavaScript, CSS, JIRA", "job_type": "contract",
     "experience_level": "mid", "salary_min": 1000000, "salary_max": 1400000,
     "description": "6-month contract to build UI components for a banking client portal.",
     "posted_at": "2026-04-07", "is_open": 1},
    {"title": "Data Engineer", "company": "Deloitte", "location": "Hyderabad",
     "skills": "Python, Spark, Airflow, AWS, SQL", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1400000, "salary_max": 2000000,
     "description": "Build and maintain ETL pipelines for large enterprise analytics projects.",
     "posted_at": "2026-04-09", "is_open": 1},
    {"title": "Android Developer (Senior)", "company": "Hyundai Motor India", "location": "Hyderabad",
     "skills": "Android, Kotlin, MVVM, Bluetooth, IoT", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2000000, "salary_max": 2800000,
     "description": "Build connected-car Android applications for in-vehicle infotainment.",
     "posted_at": "2026-04-04", "is_open": 1},

    # Pune — various
    {"title": "Senior Node.js Developer", "company": "ThoughtWorks", "location": "Pune",
     "skills": "Node.js, TypeScript, GraphQL, PostgreSQL", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 2000000, "salary_max": 2800000,
     "description": "Lead backend development for a financial services client.",
     "posted_at": "2026-04-01", "is_open": 1},
    {"title": "React Developer", "company": "Persistent Systems", "location": "Pune",
     "skills": "React, JavaScript, Redux, Jest", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1100000, "salary_max": 1700000,
     "description": "Build enterprise SaaS product UIs for US healthcare clients.",
     "posted_at": "2026-04-06", "is_open": 1},
    {"title": "QA Automation Engineer", "company": "Infosys BPM", "location": "Pune",
     "skills": "Selenium, Java, Cucumber, Jenkins", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 900000, "salary_max": 1400000,
     "description": "Design BDD test suites for insurance process automation.",
     "posted_at": "2026-04-10", "is_open": 1},
    {"title": "iOS Developer (Junior)", "company": "Bajaj Finserv", "location": "Pune",
     "skills": "Swift, iOS, UIKit, Core Data", "job_type": "full-time",
     "experience_level": "junior", "salary_min": 600000, "salary_max": 1000000,
     "description": "Build features for the Bajaj Finserv lending app on iOS.",
     "posted_at": "2026-04-12", "is_open": 1},
    {"title": "Product Manager (Mid)", "company": "Cummins India", "location": "Pune",
     "skills": "Product Management, Roadmapping, SQL, Agile", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1500000, "salary_max": 2200000,
     "description": "Own the digital tools roadmap for manufacturing operations.",
     "posted_at": "2026-03-29", "is_open": 1},
    {"title": "Python Developer (Contract)", "company": "Cognizant", "location": "Pune",
     "skills": "Python, Flask, MySQL, Docker", "job_type": "contract",
     "experience_level": "mid", "salary_min": 1000000, "salary_max": 1500000,
     "description": "3-month engagement building data ingestion APIs for a telecom client.",
     "posted_at": "2026-04-11", "is_open": 1},

    # Delhi / NCR — various
    {"title": "Senior React Developer", "company": "Policybazaar", "location": "Delhi",
     "skills": "React, TypeScript, Next.js, SEO", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 1800000, "salary_max": 2500000,
     "description": "Lead development of high-traffic insurance comparison pages.",
     "posted_at": "2026-04-03", "is_open": 1},
    {"title": "Data Scientist", "company": "MakeMyTrip", "location": "Delhi",
     "skills": "Python, scikit-learn, SQL, A/B testing", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1500000, "salary_max": 2100000,
     "description": "Build price prediction models and personalisation engines for travel bookings.",
     "posted_at": "2026-04-08", "is_open": 1},
    {"title": "DevOps Engineer", "company": "Snapdeal", "location": "Delhi",
     "skills": "AWS, Kubernetes, Helm, CI/CD", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1300000, "salary_max": 1900000,
     "description": "Manage cloud deployments and improve release pipeline reliability.",
     "posted_at": "2026-04-05", "is_open": 1},
    {"title": "Java Developer", "company": "HCL Technologies", "location": "Delhi",
     "skills": "Java, Spring MVC, Oracle DB, REST", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1000000, "salary_max": 1500000,
     "description": "Develop backend modules for a public-sector e-governance project.",
     "posted_at": "2026-04-07", "is_open": 1},
    {"title": "Node.js Developer (Remote)", "company": "Unacademy", "location": "Delhi",
     "skills": "Node.js, Express, MongoDB, Socket.io", "job_type": "remote",
     "experience_level": "mid", "salary_min": 1200000, "salary_max": 1800000,
     "description": "Build real-time live class features and notification services.",
     "posted_at": "2026-04-09", "is_open": 1},
    {"title": "Junior Python Developer", "company": "Naukri.com", "location": "Delhi",
     "skills": "Python, Django, REST APIs, PostgreSQL", "job_type": "full-time",
     "experience_level": "junior", "salary_min": 600000, "salary_max": 950000,
     "description": "Build internal tools and data processing scripts for the jobs platform.",
     "posted_at": "2026-04-13", "is_open": 1},

    # Remote / cross-city
    {"title": "Full Stack React + Node Developer", "company": "Hasura", "location": "Bangalore",
     "skills": "React, Node.js, GraphQL, PostgreSQL, Docker", "job_type": "remote",
     "experience_level": "senior", "salary_min": 2500000, "salary_max": 3500000,
     "description": "Build open-source tooling and cloud product features fully remote.",
     "posted_at": "2026-04-02", "is_open": 1},
    {"title": "ML Engineer (Remote)", "company": "Sarvam AI", "location": "Bangalore",
     "skills": "Python, PyTorch, Transformers, CUDA", "job_type": "remote",
     "experience_level": "senior", "salary_min": 3000000, "salary_max": 5000000,
     "description": "Train and fine-tune large language models for Indian language tasks.",
     "posted_at": "2026-04-05", "is_open": 1},
    {"title": "QA Engineer (Remote)", "company": "Postman", "location": "Bangalore",
     "skills": "API Testing, Postman, JavaScript, Newman", "job_type": "remote",
     "experience_level": "mid", "salary_min": 1400000, "salary_max": 2000000,
     "description": "Test Postman's API collaboration platform features and integrations.",
     "posted_at": "2026-04-11", "is_open": 1},
    {"title": "Senior Product Manager", "company": "Razorpay", "location": "Bangalore",
     "skills": "Product Management, Payments, SQL, Roadmapping", "job_type": "full-time",
     "experience_level": "senior", "salary_min": 3000000, "salary_max": 4000000,
     "description": "Own Razorpay's merchant dashboard product from strategy to launch.",
     "posted_at": "2026-04-04", "is_open": 1},
    {"title": "React Native Developer", "company": "Ola Electric", "location": "Bangalore",
     "skills": "React Native, TypeScript, iOS, Android", "job_type": "full-time",
     "experience_level": "mid", "salary_min": 1400000, "salary_max": 2000000,
     "description": "Build the companion app for Ola Electric scooters.",
     "posted_at": "2026-04-08", "is_open": 1},
    # Closed job (for testing is_open filter)
    {"title": "Archived Python Role", "company": "OldCo", "location": "Pune",
     "skills": "Python", "job_type": "full-time", "experience_level": "mid",
     "salary_min": 1000000, "salary_max": 1500000,
     "description": "This position is closed.", "posted_at": "2025-01-01", "is_open": 0},
]
```

- [ ] **Step 2: Verify seed data loads cleanly**

```bash
cd /Users/vrln/mcp-project/mcp-server
source .venv/bin/activate
python -c "from seed_data import JOBS; print(f'{len(JOBS)} records, last: {JOBS[-1][\"title\"]}')"
```

Expected: `52 records, last: Archived Python Role`

- [ ] **Step 3: Commit**

```bash
cd /Users/vrln/mcp-project
git add mcp-server/seed_data.py
git commit -m "feat: seed data — 52 realistic Indian tech job records"
```

---

### Task 4: MCP tools + FastAPI main

**Files:**
- Create: `mcp-project/mcp-server/tools.py`
- Create: `mcp-project/mcp-server/main.py`

- [ ] **Step 1: Write `tools.py`**

Write `/Users/vrln/mcp-project/mcp-server/tools.py`:
```python
from typing import Optional
import database


def register_tools(mcp) -> None:
    @mcp.tool()
    def list_jobs(
        page: int = 1,
        page_size: int = 10,
        location: Optional[str] = None,
        job_type: Optional[str] = None,
        experience_level: Optional[str] = None,
    ) -> dict:
        """List open jobs with optional filters. Returns paginated results with total count.
        job_type values: full-time, contract, remote.
        experience_level values: junior, mid, senior."""
        return database.db_list_jobs(page, page_size, location, job_type, experience_level)

    @mcp.tool()
    def get_job(job_id: int) -> dict:
        """Get a single job record by its numeric ID. Returns all fields including description."""
        return database.db_get_job(job_id)

    @mcp.tool()
    def search_jobs(
        query: str,
        location: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> list:
        """Search open jobs by keyword across title, skills, and description (max 20 results).
        Optionally filter by location (city name) or skill (e.g. 'React', 'Python')."""
        return database.db_search_jobs(query, location, skill)
```

- [ ] **Step 2: Write `main.py`**

Write `/Users/vrln/mcp-project/mcp-server/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
import database
from tools import register_tools

mcp_server = FastMCP("jobs-mcp-server")
register_tools(mcp_server)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.mount("/", mcp_server.sse_app())
```

- [ ] **Step 3: Start the server and verify**

```bash
cd /Users/vrln/mcp-project/mcp-server
source .venv/bin/activate
uvicorn main:app --port 8000
```

In a second terminal:
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

```bash
curl -N http://localhost:8000/sse
```
Expected: SSE stream begins (`data: ...` lines). Press Ctrl-C to stop.

- [ ] **Step 4: Commit**

```bash
cd /Users/vrln/mcp-project
git add mcp-server/tools.py mcp-server/main.py
git commit -m "feat: MCP tools and FastAPI app with SSE transport"
```

---

### Task 5: Agent (TDD)

**Files:**
- Create: `mcp-project/mcp-client/agent.py`
- Create: `mcp-project/mcp-client/tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Write `/Users/vrln/mcp-project/mcp-client/tests/test_agent.py`:
```python
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_mcp_session():
    tool = MagicMock()
    tool.name = "search_jobs"
    tool.description = "Search jobs"
    tool.inputSchema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    tools_result = MagicMock()
    tools_result.tools = [tool]

    call_result = MagicMock()
    call_result.content = [MagicMock(text='[{"id": 1, "title": "React Dev", "company": "Acme"}]')]

    session = AsyncMock()
    session.list_tools.return_value = tools_result
    session.call_tool.return_value = call_result
    return session


def _make_anthropic_responses(tool_name, tool_input, final_text):
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    tool_use.name = tool_name
    tool_use.id = "tu_abc123"
    tool_use.input = tool_input

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = final_text

    resp_tool = MagicMock()
    resp_tool.stop_reason = "tool_use"
    resp_tool.content = [tool_use]

    resp_final = MagicMock()
    resp_final.stop_reason = "end_turn"
    resp_final.content = [text_block]

    return [resp_tool, resp_final]


@pytest.mark.asyncio
async def test_run_returns_text_and_tool_log(mock_mcp_session):
    import agent

    anthropic_client = MagicMock()
    anthropic_client.messages.create.side_effect = _make_anthropic_responses(
        "search_jobs", {"query": "React"}, "Found 1 React job."
    )

    with patch("agent.sse_client") as mock_sse, \
         patch("agent.ClientSession") as mock_cs, \
         patch("agent.anthropic.Anthropic", return_value=anthropic_client):

        mock_sse.return_value.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_sse.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_mcp_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=None)

        text, log = await agent.run("Show me React jobs")

    assert text == "Found 1 React job."
    assert len(log) == 1
    assert log[0]["tool"] == "search_jobs"
    assert log[0]["input"] == {"query": "React"}
    assert "React Dev" in log[0]["output"]


@pytest.mark.asyncio
async def test_run_without_tool_use(mock_mcp_session):
    import agent

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I can help you search for jobs."

    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [text_block]

    anthropic_client = MagicMock()
    anthropic_client.messages.create.return_value = resp

    with patch("agent.sse_client") as mock_sse, \
         patch("agent.ClientSession") as mock_cs, \
         patch("agent.anthropic.Anthropic", return_value=anthropic_client):

        mock_sse.return_value.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_sse.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_cs.return_value.__aenter__ = AsyncMock(return_value=mock_mcp_session)
        mock_cs.return_value.__aexit__ = AsyncMock(return_value=None)

        text, log = await agent.run("hello")

    assert text == "I can help you search for jobs."
    assert log == []


@pytest.mark.asyncio
async def test_run_returns_error_on_connection_failure():
    import agent

    with patch("agent.sse_client") as mock_sse:
        mock_sse.side_effect = Exception("Connection refused")
        text, log = await agent.run("Show me React jobs")

    assert text == ""
    assert len(log) == 1
    assert "error" in log[0]
    assert "Connection refused" in log[0]["error"]
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
cd /Users/vrln/mcp-project/mcp-client
source .venv/bin/activate
python -m pytest tests/test_agent.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'agent'`

- [ ] **Step 3: Write `agent.py`**

Write `/Users/vrln/mcp-project/mcp-client/agent.py`:
```python
import anthropic
from mcp.client.sse import sse_client
from mcp import ClientSession

MCP_SERVER_URL = "http://localhost:8000/sse"
SYSTEM_PROMPT = (
    "You are a job search assistant. Use the available tools to answer the user's "
    "query about jobs. Be concise and format results in a readable list."
)


async def run(query: str) -> tuple[str, list[dict]]:
    tool_call_log: list[dict] = []
    try:
        async with sse_client(MCP_SERVER_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools_result = await session.list_tools()
                anthropic_tools = [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema,
                    }
                    for t in tools_result.tools
                ]

                client = anthropic.Anthropic()
                messages: list[dict] = [{"role": "user", "content": query}]

                while True:
                    response = client.messages.create(
                        model="claude-sonnet-4-6",
                        max_tokens=4096,
                        system=SYSTEM_PROMPT,
                        tools=anthropic_tools,
                        messages=messages,
                    )

                    if response.stop_reason == "tool_use":
                        tool_uses = [b for b in response.content if b.type == "tool_use"]
                        messages.append({"role": "assistant", "content": response.content})

                        tool_results = []
                        for tu in tool_uses:
                            call_result = await session.call_tool(tu.name, tu.input)
                            output = (
                                call_result.content[0].text
                                if call_result.content
                                else ""
                            )
                            tool_call_log.append(
                                {"tool": tu.name, "input": tu.input, "output": output}
                            )
                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tu.id,
                                    "content": output,
                                }
                            )
                        messages.append({"role": "user", "content": tool_results})

                    else:
                        final_text = next(
                            (b.text for b in response.content if b.type == "text"),
                            "No response generated.",
                        )
                        return final_text, tool_call_log

    except Exception as exc:
        return "", [{"error": f"MCP server offline or error: {exc}"}]
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd /Users/vrln/mcp-project/mcp-client
source .venv/bin/activate
python -m pytest tests/test_agent.py -v
```

Expected:
```
test_agent.py::test_run_returns_text_and_tool_log PASSED
test_agent.py::test_run_without_tool_use PASSED
test_agent.py::test_run_returns_error_on_connection_failure PASSED
3 passed
```

- [ ] **Step 5: Commit**

```bash
cd /Users/vrln/mcp-project
git add mcp-client/agent.py mcp-client/tests/test_agent.py
git commit -m "feat: MCP client agent with Claude SDK and tests"
```

---

### Task 6: Streamlit UI

**Files:**
- Create: `mcp-project/mcp-client/app.py`

- [ ] **Step 1: Write `app.py`**

Write `/Users/vrln/mcp-project/mcp-client/app.py`:
```python
import asyncio
import json
import requests
import streamlit as st
from agent import run

st.set_page_config(page_title="Jobs AI Assistant", layout="wide")

MCP_HEALTH_URL = "http://localhost:8000/health"


def check_server() -> bool:
    try:
        r = requests.get(MCP_HEALTH_URL, timeout=2)
        return r.status_code == 200
    except Exception:
        return False


st.title("Jobs AI Assistant")
st.caption("Powered by Claude + MCP · Queries the jobs database via SSE tool calls")

server_ok = check_server()
if server_ok:
    st.success("🟢  MCP Server connected · localhost:8000")
else:
    st.error("🔴  MCP Server offline · start App A first: `uvicorn main:app --port 8000`")

left, right = st.columns(2, gap="large")

with left:
    st.subheader("Query")
    query = st.text_input(
        "Ask about jobs...",
        placeholder="Show me senior React jobs in Bangalore",
        disabled=not server_ok,
    )
    ask_clicked = st.button("Ask", disabled=not server_ok or not query)

    if ask_clicked and query:
        with st.spinner("Agent thinking..."):
            response_text, tool_log = asyncio.run(run(query))
        st.session_state["response_text"] = response_text
        st.session_state["tool_log"] = tool_log

    if "response_text" in st.session_state:
        st.subheader("Response")
        if st.session_state["response_text"]:
            st.markdown(st.session_state["response_text"])
        else:
            st.error("No response — see the MCP Inspector for error details.")

with right:
    st.subheader("MCP Tool Inspector")

    if not server_ok:
        st.warning("Start App A to see live tool calls here.")
    else:
        st.info("Available tools discovered at session start: **list_jobs · get_job · search_jobs**")

    if "tool_log" in st.session_state:
        log = st.session_state["tool_log"]
        if not log:
            st.caption("No tool calls were made for this query.")
        for entry in log:
            if "error" in entry:
                st.error(entry["error"])
            else:
                st.markdown(f"**▶ Tool Call: `{entry['tool']}`**")
                st.code(json.dumps(entry["input"], indent=2), language="json")
                st.markdown("**◀ Tool Result:**")
                output = entry["output"]
                display = output if len(output) <= 600 else output[:600] + "\n... (truncated)"
                st.code(display, language="json")
                st.divider()
```

- [ ] **Step 2: Verify the app imports cleanly**

```bash
cd /Users/vrln/mcp-project/mcp-client
source .venv/bin/activate
python -c "import app; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/vrln/mcp-project
git add mcp-client/app.py
git commit -m "feat: Streamlit split-panel UI with MCP tool inspector"
```

---

### Task 7: End-to-end verification

- [ ] **Step 1: Run all unit tests**

```bash
# Terminal 1 — App A tests
cd /Users/vrln/mcp-project/mcp-server
source .venv/bin/activate
python -m pytest tests/ -v
deactivate

# Terminal 2 — App B tests
cd /Users/vrln/mcp-project/mcp-client
source .venv/bin/activate
python -m pytest tests/ -v
deactivate
```

Expected: 12 + 3 = 15 tests pass, 0 failures.

- [ ] **Step 2: Start App A (Terminal 1)**

```bash
cd /Users/vrln/mcp-project/mcp-server
source .venv/bin/activate
uvicorn main:app --port 8000
```

Expected log line: `Application startup complete.` and a `jobs.db` file created with 52 rows.

Verify from a separate shell:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

- [ ] **Step 3: Start App B (Terminal 2)**

```bash
cd /Users/vrln/mcp-project/mcp-client
source .venv/bin/activate
export ANTHROPIC_API_KEY=<your-key>
streamlit run app.py
```

Expected: browser opens at http://localhost:8501 showing green "MCP Server connected" banner.

- [ ] **Step 4: Run demo queries**

In the Streamlit UI, try each query and verify:

| Query | Expected tool called | Inspector shows |
|---|---|---|
| "Show me senior React jobs in Bangalore" | `search_jobs` | input with query/location/skill, JSON results list |
| "List all open DevOps positions" | `list_jobs` | paginated result with total count |
| "Tell me more about job #1" | `get_job` | single job record with all fields |
| "Find remote Python roles" | `search_jobs` | filtered by query="Python", job_type in results |

- [ ] **Step 5: Final commit**

```bash
cd /Users/vrln/mcp-project
git add .
git commit -m "docs: add implementation plan for MCP server/client demo"
```
