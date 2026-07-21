import pytest
from unittest.mock import MagicMock, patch
from app.services.job_service import save_jobs
from app.database.models.job import Job


def _make_job(remote_id: str) -> dict:
    return {
        "remote_id": remote_id,
        "title": "Test Job",
        "company_name": "TestCorp",
        "company_country": "India",
        "category": "Software Development",
        "job_link": "https://remote.io/jobs/test",
        "application_url": "https://apply.example.com/test",
        "description": "Test description",
        "salary": None,
        "key_preferences": '["Python"]',
        "published_at": None,
    }


def test_save_jobs_inserts_new_jobs():
    db = MagicMock()
    # Simulate no existing jobs in DB
    db.query.return_value.all.return_value = []

    jobs = [_make_job("new-id-001"), _make_job("new-id-002")]
    inserted, _ = save_jobs(db, jobs)

    assert inserted == 2
    db.bulk_save_objects.assert_called_once()
    db.commit.assert_called()


def test_save_jobs_skips_duplicates():
    db = MagicMock()
    # Simulate one existing job
    db.query.return_value.all.return_value = [("existing-id-001",)]

    jobs = [_make_job("existing-id-001"), _make_job("new-id-002")]
    inserted, _ = save_jobs(db, jobs)

    assert inserted == 1


def test_save_jobs_empty_input():
    db = MagicMock()
    inserted, _ = save_jobs(db, [])
    assert inserted == 0
    db.bulk_save_objects.assert_not_called()


def test_save_jobs_all_duplicates():
    db = MagicMock()
    db.query.return_value.all.return_value = [("id-001",), ("id-002",)]

    jobs = [_make_job("id-001"), _make_job("id-002")]
    inserted, _ = save_jobs(db, jobs)

    assert inserted == 0