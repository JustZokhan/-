from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    total_sum = Column(BigInteger, default=0)

    results = relationship("Result", back_populates="employee", cascade="all, delete-orphan")

class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    day = Column(String, nullable=False)  # 'ПТ','СБ','ПН','ВТ','СР','ЧТ'
    amount = Column(BigInteger, default=0)

    employee = relationship("Employee", back_populates="results")

    __table_args__ = (
        UniqueConstraint('employee_id', 'day', name='uix_employee_day'),
    )
