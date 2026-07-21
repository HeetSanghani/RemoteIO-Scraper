from sqlalchemy import Column, Integer, String
from app.database.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False, index=True)
    company_slug = Column(String, nullable=True, unique=True)
    logo_url = Column(String, nullable=True)

    def __repr__(self):
        return f"<Company id={self.id} name={self.company_name}>"