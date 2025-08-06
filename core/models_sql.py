"""
SQLModel database models for ProofKit

Defines all database entities: User, Organization, Subscription, Plan, Job, QuotaCounter, AuditLog
Uses SQLModel for type-safe ORM with async PostgreSQL support
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID, uuid4
from enum import Enum
from sqlmodel import Field, SQLModel, Relationship, Column, JSON


class PlanTier(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditAction(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    QA_APPROVAL = "qa_approval"
    SETTING_CHANGE = "setting_change"
    CERTIFICATE_CREATED = "certificate_created"
    SUBSCRIPTION_CHANGE = "subscription_change"


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    # Relationships
    users: List["User"] = Relationship(back_populates="organization")
    subscriptions: List["Subscription"] = Relationship(back_populates="organization")


class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    name: Optional[str] = None
    organization_id: Optional[UUID] = Field(foreign_key="organizations.id", index=True)
    is_active: bool = Field(default=True)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    # Relationships
    organization: Optional[Organization] = Relationship(back_populates="users")
    jobs: List["Job"] = Relationship(back_populates="user")
    audit_logs: List["AuditLog"] = Relationship(back_populates="user")
    quota_counters: List["QuotaCounter"] = Relationship(back_populates="user")


class Plan(SQLModel, table=True):
    __tablename__ = "plans"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    tier: PlanTier
    monthly_quota: int  # Number of certificates per month
    price_cents: int  # Price in cents (0 for free)
    stripe_price_id: Optional[str] = None
    features: dict = Field(default_factory=dict, sa_column=Column(JSON))
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    subscriptions: List["Subscription"] = Relationship(back_populates="plan")


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    organization_id: Optional[UUID] = Field(foreign_key="organizations.id", index=True)
    plan_id: UUID = Field(foreign_key="plans.id", index=True)
    stripe_subscription_id: Optional[str] = Field(unique=True, index=True)
    status: str = Field(default="active")  # active, canceled, past_due
    current_period_start: datetime
    current_period_end: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    
    # Relationships
    user: User = Relationship()
    organization: Optional[Organization] = Relationship(back_populates="subscriptions")
    plan: Plan = Relationship(back_populates="subscriptions")


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    spec_name: str
    csv_filename: str
    result_pass: bool = Field(default=False, index=True, alias="pass_bool")
    pdf_url: Optional[str] = None
    evidence_url: Optional[str] = None
    error_message: Optional[str] = None
    metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    completed_at: Optional[datetime] = None
    
    # Relationships
    user: User = Relationship(back_populates="jobs")
    
    @property
    def pass_bool(self) -> bool:
        """Alias for result_pass to match API requirements."""
        return self.result_pass


class QuotaCounter(SQLModel, table=True):
    __tablename__ = "quota_counters"
    __table_args__ = (
        {"extend_existing": True}
    )
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    year_month: str = Field(index=True)  # Format: "2025-08"
    count: int = Field(default=0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Composite index for fast lookups
    __table_args__ = (
        {"postgresql_indexes": [
            {"name": "idx_user_month", "columns": ["user_id", "year_month"], "unique": True}
        ]}
    )
    
    # Relationships
    user: User = Relationship(back_populates="quota_counters")


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(foreign_key="users.id", index=True)
    action: AuditAction = Field(index=True)
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: dict = Field(default_factory=dict, sa_column=Column(JSON))
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationships
    user: Optional[User] = Relationship(back_populates="audit_logs")