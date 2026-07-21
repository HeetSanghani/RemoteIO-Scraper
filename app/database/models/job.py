from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index
from sqlalchemy.sql import func
from app.database.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    remote_id = Column(String(100), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    company_name = Column(String(200), nullable=True)
    company_country = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    job_link = Column(String(1000), nullable=True)
    application_url = Column(String(1000), nullable=True)
    description = Column(Text, nullable=True)
    salary = Column(String(200), nullable=True)
    key_preferences = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    scraped_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False          # ← was nullable=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True
    )
    is_active = Column(Boolean, default=True, nullable=False)  # ← was nullable=True

    # Composite indexes for common filter queries
    __table_args__ = (
        Index("ix_jobs_category", "category"),
        Index("ix_jobs_company_country", "company_country"),
        Index("ix_jobs_published_at", "published_at"),
        Index("ix_jobs_is_active", "is_active"),
        Index("ix_jobs_company_name", "company_name"),
        # Composite: most common query pattern
        Index("ix_jobs_active_published", "is_active", "published_at"),
    )

    def __repr__(self):
        return f"<Job id={self.id} title={self.title} company={self.company_name}>"