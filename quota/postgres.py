"""
Quota management with PostgreSQL

Tracks certificate usage per user per month
Enforces plan limits with transactional consistency
"""

from datetime import datetime, timezone
from typing import Tuple, Optional
from uuid import UUID
from sqlmodel import select, and_
from sqlalchemy import func
from core.db import get_db_session
from core.models_sql import User, Job, JobStatus, QuotaCounter, Subscription, Plan, AuditLog, AuditAction
from core.logging import get_logger

logger = get_logger(__name__)


async def get_current_month_key() -> str:
    """Get current year-month key for quota tracking"""
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


async def get_user_quota(user_id: UUID) -> Tuple[int, int]:
    """
    Get user's quota usage and limit for current month
    Returns: (used, limit)
    """
    async with get_db_session() as session:
        # Get user with subscription and plan
        user = await session.get(User, user_id)
        if not user:
            return (0, 0)
        
        # Get active subscription
        result = await session.execute(
            select(Subscription)
            .where(
                and_(
                    Subscription.user_id == user_id,
                    Subscription.status == "active"
                )
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        subscription = result.scalar_one_or_none()
        
        # Default to free plan if no subscription
        if not subscription:
            result = await session.execute(
                select(Plan).where(Plan.tier == "free")
            )
            plan = result.scalar_one_or_none()
            monthly_limit = plan.monthly_quota if plan else 5
        else:
            # Get plan from subscription
            plan = await session.get(Plan, subscription.plan_id)
            monthly_limit = plan.monthly_quota if plan else 5
        
        # Get current month usage
        month_key = await get_current_month_key()
        result = await session.execute(
            select(QuotaCounter)
            .where(
                and_(
                    QuotaCounter.user_id == user_id,
                    QuotaCounter.year_month == month_key
                )
            )
        )
        counter = result.scalar_one_or_none()
        used = counter.count if counter else 0
        
        return (used, monthly_limit)


async def check_quota(user_id: UUID) -> bool:
    """
    Check if user has quota available
    Returns True if quota available, False if exceeded
    """
    used, limit = await get_user_quota(user_id)
    return used < limit


async def record_job(
    user_id: UUID,
    spec_name: str,
    csv_filename: str,
    result_pass: bool,
    pdf_url: Optional[str] = None,
    evidence_url: Optional[str] = None,
    metadata: Optional[dict] = None
) -> UUID:
    """
    Record a job and increment quota counter
    Returns job ID
    Raises ValueError if quota exceeded
    """
    async with get_db_session() as session:
        # Start transaction
        async with session.begin():
            # Check quota with row lock
            month_key = await get_current_month_key()
            
            # Get or create quota counter with lock
            result = await session.execute(
                select(QuotaCounter)
                .where(
                    and_(
                        QuotaCounter.user_id == user_id,
                        QuotaCounter.year_month == month_key
                    )
                )
                .with_for_update()  # Lock row for update
            )
            counter = result.scalar_one_or_none()
            
            if not counter:
                # Create new counter
                counter = QuotaCounter(
                    user_id=user_id,
                    year_month=month_key,
                    count=0
                )
                session.add(counter)
            
            # Get user's quota limit
            used, limit = await get_user_quota(user_id)
            
            # Check if quota exceeded
            if counter.count >= limit:
                raise ValueError(f"Monthly quota exceeded: {counter.count}/{limit}")
            
            # Create job record
            job = Job(
                user_id=user_id,
                spec_name=spec_name,
                csv_filename=csv_filename,
                result_pass=result_pass,
                status=JobStatus.COMPLETED,
                pdf_url=pdf_url,
                evidence_url=evidence_url,
                metadata=metadata or {},
                completed_at=datetime.now(timezone.utc)
            )
            session.add(job)
            
            # Increment quota counter
            counter.count += 1
            counter.updated_at = datetime.now(timezone.utc)
            
            # Create audit log
            audit_log = AuditLog(
                user_id=user_id,
                action=AuditAction.CERTIFICATE_CREATED,
                resource_type="job",
                resource_id=str(job.id),
                details={
                    "spec_name": spec_name,
                    "result": "PASS" if result_pass else "FAIL",
                    "quota_used": f"{counter.count}/{limit}"
                }
            )
            session.add(audit_log)
            
            # Commit transaction
            await session.commit()
            
            logger.info(f"Recorded job {job.id} for user {user_id} (quota: {counter.count}/{limit})")
            return job.id


async def get_recent_jobs(user_id: UUID, limit: int = 20) -> list:
    """
    Get user's recent jobs
    """
    async with get_db_session() as session:
        result = await session.execute(
            select(Job)
            .where(Job.user_id == user_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()


async def get_job_by_id(job_id: UUID, user_id: Optional[UUID] = None) -> Optional[Job]:
    """
    Get job by ID, optionally filtered by user
    """
    async with get_db_session() as session:
        query = select(Job).where(Job.id == job_id)
        
        if user_id:
            query = query.where(Job.user_id == user_id)
        
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def reset_user_quota(user_id: UUID, month_key: Optional[str] = None):
    """
    Reset user's quota counter (admin function)
    """
    if not month_key:
        month_key = await get_current_month_key()
    
    async with get_db_session() as session:
        result = await session.execute(
            select(QuotaCounter)
            .where(
                and_(
                    QuotaCounter.user_id == user_id,
                    QuotaCounter.year_month == month_key
                )
            )
        )
        counter = result.scalar_one_or_none()
        
        if counter:
            counter.count = 0
            counter.updated_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info(f"Reset quota for user {user_id} for month {month_key}")