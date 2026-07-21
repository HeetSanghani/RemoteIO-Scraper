from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from sqlalchemy.sql import func
from app.database.database import Base


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    jobs_found = Column(Integer, default=0, nullable=False)
    jobs_inserted = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Float, nullable=True)   # ← new: track scrape speed
    status = Column(String(20), default="running", nullable=False)
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<ScrapeLog id={self.id} status={self.status} inserted={self.jobs_inserted}>"