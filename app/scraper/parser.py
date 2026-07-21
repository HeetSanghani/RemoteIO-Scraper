import json
from datetime import datetime
from app.utils.logger import logger


def parse_job(raw: dict) -> dict | None:
    try:
        remote_id = str(raw.get("id", "")).strip()
        if not remote_id:
            logger.warning("Skipping job with no remote_id")
            return None

        # Skill tags
        skill_tags = raw.get("skillTags") or []
        key_preferences = json.dumps(skill_tags) if isinstance(skill_tags, list) else str(skill_tags)

        # Country from locations list
        locations = raw.get("locations", [])
        company_country = locations[0].get("name", "") if locations else raw.get("location", "")

        # Salary — use salaryRange or build from min/max
        salary = raw.get("salaryRange", "")
        if not salary:
            sal_min = raw.get("salaryMin") or raw.get("salary_usd_yearly_min")
            sal_max = raw.get("salaryMax") or raw.get("salary_usd_yearly_max")
            currency = raw.get("salaryCurrency", "USD")
            if sal_min and sal_max:
                salary = f"{currency} {sal_min} - {sal_max}"

        # Published date
        published_at = None
        published_raw = raw.get("publishedAt")
        if published_raw:
            try:
                published_at = datetime.fromisoformat(
                    str(published_raw).replace("Z", "+00:00")
                )
            except Exception:
                published_at = None

        return {
            "remote_id": remote_id,
            "title": raw.get("jobTitle", "").strip(),
            "company_name": raw.get("companyName") or raw.get("displayName", ""),
            "company_country": company_country,
            "category": raw.get("category", ""),
            "job_link": "https://remote.io" + raw.get("jobUrl", ""),
            "application_url": raw.get("applicationUrl", ""),
            "description": raw.get("description") or raw.get("snippet", ""),
            "salary": salary,
            "key_preferences": key_preferences,
            "published_at": published_at,
        }

    except Exception as e:
        logger.error(f"Error parsing job: {e} | raw: {raw}")
        return None


def parse_jobs(raw_jobs: list[dict]) -> list[dict]:
    parsed = []
    for raw in raw_jobs:
        job = parse_job(raw)
        if job:
            parsed.append(job)
    logger.info(f"Parsed {len(parsed)} valid jobs out of {len(raw_jobs)}")
    return parsed