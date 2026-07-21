from pydantic import BaseModel
from typing import Optional, List


class CategoryStat(BaseModel):
    category: str
    count: int


class CountryStat(BaseModel):
    country: str
    count: int


class CompanyStat(BaseModel):
    company: str
    count: int


class SkillStat(BaseModel):
    skill: str
    count: int


class ScrapeRecord(BaseModel):
    started_at: Optional[str]
    completed_at: Optional[str]
    status: Optional[str]
    jobs_found: Optional[int]
    jobs_inserted: Optional[int]
    error_message: Optional[str]


class DailyGrowth(BaseModel):
    date: str
    jobs_scraped: int


class AnalyticsResponse(BaseModel):
    # ── Counts ────────────────────────────────────────────────────────────────
    total_jobs: int
    jobs_today: int
    jobs_this_week: int
    jobs_with_salary: int
    salary_coverage_pct: float
    duplicate_count: int

    # ── Rankings ──────────────────────────────────────────────────────────────
    top_categories: List[CategoryStat]
    top_countries: List[CountryStat]
    top_companies: List[CompanyStat]
    top_skills: List[SkillStat]

    # ── Trends ────────────────────────────────────────────────────────────────
    daily_growth: List[DailyGrowth]

    # ── Scrape audit ──────────────────────────────────────────────────────────
    scrape_history: List[ScrapeRecord]