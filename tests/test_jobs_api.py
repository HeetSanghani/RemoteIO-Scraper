import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

from sqlalchemy.pool import StaticPool

from main import app
from app.database.database import Base, get_db
from app.database.models.job import Job
from app.database.models.company import Company
from app.database.models.scrape_log import ScrapeLog

# Setup test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True, scope="module")
def setup_database():
    # Create tables
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Seed dummy jobs
    jobs = [
        Job(
            id=1,
            remote_id="id-1",
            title="Python Developer",
            company_name="Datadog",
            company_country="United States",
            category="Software Development",
            job_link="https://example.com/1",
            application_url="https://example.com/1/apply",
            salary="$100,000",
            key_preferences='["Python", "FastAPI"]',
            is_active=True,
            scraped_at=datetime.now(timezone.utc),
            published_at=datetime.now(timezone.utc)
        ),
        Job(
            id=2,
            remote_id="id-2",
            title="React Engineer",
            company_name="DesignCorp",
            company_country="Canada",
            category="Software Development",
            job_link="https://example.com/2",
            application_url="https://example.com/2/apply",
            salary="$90,000",
            key_preferences='["React", "TypeScript"]',
            is_active=True,
            scraped_at=datetime.now(timezone.utc),
            published_at=datetime.now(timezone.utc)
        ),
        Job(
            id=3,
            remote_id="id-3",
            title="Product Manager",
            company_name="BizCorp",
            company_country="United States",
            category="Management",
            job_link="https://example.com/3",
            application_url="https://example.com/3/apply",
            salary=None,
            key_preferences='["Agile", "Scrum"]',
            is_active=True,
            scraped_at=datetime.now(timezone.utc),
            published_at=datetime.now(timezone.utc)
        ),
    ]
    db.bulk_save_objects(jobs)
    
    # Seed scrape log
    db.add(ScrapeLog(
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        status="success",
        jobs_found=3,
        jobs_inserted=3
    ))
    
    db.commit()
    db.close()
    
    # Override get_db dependency
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
            
    app.dependency_overrides[get_db] = override_get_db
    yield
    # Cleanup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


# ── /api/v1/jobs/ ─────────────────────────────────────────────────────────────

def test_list_jobs_returns_paginated_response():
    response = client.get("/api/v1/jobs/?page=1&page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


def test_list_jobs_pagination_limits():
    response = client.get("/api/v1/jobs/?page=1&page_size=3")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) <= 3


def test_list_jobs_invalid_page():
    response = client.get("/api/v1/jobs/?page=0")
    assert response.status_code == 422  # FastAPI validation error


def test_list_jobs_invalid_page_size():
    response = client.get("/api/v1/jobs/?page_size=999")
    assert response.status_code == 422


def test_list_jobs_sorting():
    response = client.get("/api/v1/jobs/?sort_by=title&sort_order=asc&page_size=5")
    assert response.status_code == 200


# ── /api/v1/jobs/search ───────────────────────────────────────────────────────

def test_search_with_keyword():
    response = client.get("/api/v1/jobs/search?keyword=python&page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert isinstance(data["jobs"], list)


def test_search_without_params_returns_400():
    response = client.get("/api/v1/jobs/search")
    assert response.status_code == 400


def test_search_by_country():
    response = client.get("/api/v1/jobs/search?country=United+States&page_size=5")
    assert response.status_code == 200


# ── /api/v1/jobs/filter ───────────────────────────────────────────────────────

def test_filter_by_category():
    response = client.get("/api/v1/jobs/filter?category=Software+Development&page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0


def test_filter_without_params_returns_400():
    response = client.get("/api/v1/jobs/filter")
    assert response.status_code == 400


def test_filter_by_company():
    response = client.get("/api/v1/jobs/filter?company=Datadog&page_size=5")
    assert response.status_code == 200


# ── /api/v1/jobs/{job_id} ─────────────────────────────────────────────────────

def test_get_job_by_valid_id():
    response = client.get("/api/v1/jobs/1")
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "title" in data
    assert "company_name" in data
    assert isinstance(data["key_preferences"], list)


def test_get_job_by_invalid_id():
    response = client.get("/api/v1/jobs/999999")
    assert response.status_code == 404


# ── /api/v1/analytics ─────────────────────────────────────────────────────────

def test_analytics_response_shape():
    response = client.get("/api/v1/analytics")
    assert response.status_code == 200
    data = response.json()
    assert "total_jobs" in data
    assert "jobs_today" in data
    assert "top_categories" in data
    assert "top_skills" in data
    assert "salary_coverage_pct" in data


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200


# ── API Key Protection Tests ──────────────────────────────────────────────────
import os

def test_scrape_endpoint_requires_api_key():
    response = client.post("/api/v1/jobs/scrape", json={"limit": 30})
    assert response.status_code == 403
    assert "Unauthorized: Invalid or missing API Key" in response.json()["detail"]


def test_scrape_metadata_endpoint_requires_api_key():
    response = client.post("/api/v1/jobs/scrape/metadata", json={})
    assert response.status_code == 403
    assert "Unauthorized: Invalid or missing API Key" in response.json()["detail"]


def test_export_all_endpoint_requires_api_key():
    response = client.get("/api/v1/jobs/scrape/export/all/some-task-id")
    assert response.status_code == 403
    assert "Unauthorized: Invalid or missing API Key" in response.json()["detail"]


def test_export_new_endpoint_requires_api_key():
    response = client.get("/api/v1/jobs/scrape/export/new/some-task-id")
    assert response.status_code == 403
    assert "Unauthorized: Invalid or missing API Key" in response.json()["detail"]


def test_scrape_endpoint_accepts_valid_api_key_header():
    with patch.dict(os.environ, {"API_KEY": "test-secret-key"}):
        with patch("app.api.routes.jobs.scrape_and_save_jobs.delay") as mock_delay:
            mock_task = MagicMock()
            mock_task.id = "mock-task-id"
            mock_delay.return_value = mock_task
            
            headers = {"X-API-Key": "test-secret-key"}
            response = client.post("/api/v1/jobs/scrape", json={"limit": 30}, headers=headers)
            assert response.status_code == 202
            assert response.json()["task_id"] == "mock-task-id"


def test_scrape_endpoint_accepts_valid_api_key_query_param():
    with patch.dict(os.environ, {"API_KEY": "test-secret-key"}):
        with patch("app.api.routes.jobs.scrape_and_save_jobs.delay") as mock_delay:
            mock_task = MagicMock()
            mock_task.id = "mock-task-id"
            mock_delay.return_value = mock_task
            
            response = client.post("/api/v1/jobs/scrape?api_key=test-secret-key", json={"limit": 30})
            assert response.status_code == 202
            assert response.json()["task_id"] == "mock-task-id"