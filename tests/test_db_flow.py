"""
Database flow tests

Tests user creation, job recording, and quota enforcement
"""

import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from sqlmodel import select
from core.db import get_db_session, init_db
from core.models_sql import User, Plan, Subscription, Job, QuotaCounter
from quota.postgres import record_job, get_user_quota, check_quota, get_recent_jobs


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def setup_db():
    """Setup test database"""
    await init_db()
    
    # Create test plans
    async with get_db_session() as session:
        # Check if plans exist
        result = await session.execute(select(Plan).where(Plan.tier == "free"))
        if not result.scalar_one_or_none():
            free_plan = Plan(
                name="Free",
                tier="free",
                monthly_quota=2,  # Low quota for testing
                price_cents=0,
                features={"watermark": True}
            )
            session.add(free_plan)
            await session.commit()


@pytest.fixture
async def test_user(setup_db):
    """Create test user"""
    async with get_db_session() as session:
        user = User(
            email=f"test_{uuid4().hex[:8]}@example.com",
            name="Test User",
            is_active=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_create_user(setup_db):
    """Test user creation"""
    async with get_db_session() as session:
        # Create user
        user = User(
            email=f"new_{uuid4().hex[:8]}@example.com",
            name="New User",
            is_active=True
        )
        session.add(user)
        await session.commit()
        
        # Verify user exists
        result = await session.execute(
            select(User).where(User.email == user.email)
        )
        fetched_user = result.scalar_one_or_none()
        
        assert fetched_user is not None
        assert fetched_user.email == user.email
        assert fetched_user.name == "New User"
        assert fetched_user.is_active is True


@pytest.mark.asyncio
async def test_record_job_and_quota(test_user):
    """Test job recording and quota enforcement"""
    # Get initial quota
    used, limit = await get_user_quota(test_user.id)
    assert used == 0
    assert limit == 2  # Free plan limit
    
    # Record first job
    job1_id = await record_job(
        user_id=test_user.id,
        spec_name="test_spec",
        csv_filename="test1.csv",
        result_pass=True,
        metadata={"test": "data1"}
    )
    assert job1_id is not None
    
    # Check quota after first job
    used, limit = await get_user_quota(test_user.id)
    assert used == 1
    assert limit == 2
    
    # Record second job
    job2_id = await record_job(
        user_id=test_user.id,
        spec_name="test_spec",
        csv_filename="test2.csv",
        result_pass=False,
        metadata={"test": "data2"}
    )
    assert job2_id is not None
    
    # Check quota after second job
    used, limit = await get_user_quota(test_user.id)
    assert used == 2
    assert limit == 2
    
    # Third job should be blocked (quota exceeded)
    with pytest.raises(ValueError, match="Monthly quota exceeded"):
        await record_job(
            user_id=test_user.id,
            spec_name="test_spec",
            csv_filename="test3.csv",
            result_pass=True,
            metadata={"test": "data3"}
        )
    
    # Verify quota still at limit
    used, limit = await get_user_quota(test_user.id)
    assert used == 2
    assert limit == 2


@pytest.mark.asyncio
async def test_check_quota(test_user):
    """Test quota checking"""
    # Initially should have quota
    assert await check_quota(test_user.id) is True
    
    # Use up quota
    for i in range(2):  # Free plan has 2 quota
        await record_job(
            user_id=test_user.id,
            spec_name="test_spec",
            csv_filename=f"test{i}.csv",
            result_pass=True
        )
    
    # Should not have quota anymore
    assert await check_quota(test_user.id) is False


@pytest.mark.asyncio
async def test_get_recent_jobs(test_user):
    """Test fetching recent jobs"""
    # Create some jobs
    job_ids = []
    for i in range(3):
        try:
            job_id = await record_job(
                user_id=test_user.id,
                spec_name=f"spec_{i}",
                csv_filename=f"file_{i}.csv",
                result_pass=(i % 2 == 0)
            )
            job_ids.append(job_id)
        except ValueError:
            # Quota exceeded, expected
            break
    
    # Get recent jobs
    recent_jobs = await get_recent_jobs(test_user.id, limit=10)
    
    assert len(recent_jobs) >= len(job_ids)
    # Jobs should be ordered by created_at desc
    if len(recent_jobs) > 1:
        assert recent_jobs[0].created_at >= recent_jobs[1].created_at


@pytest.mark.asyncio
async def test_jobs_table_persistence(test_user):
    """Test that jobs are persisted in the database"""
    # Record a job
    job_id = await record_job(
        user_id=test_user.id,
        spec_name="persistence_test",
        csv_filename="persist.csv",
        result_pass=True,
        pdf_url="/storage/test.pdf",
        evidence_url="/storage/test.zip",
        metadata={"key": "value"}
    )
    
    # Fetch job from database
    async with get_db_session() as session:
        job = await session.get(Job, job_id)
        
        assert job is not None
        assert job.user_id == test_user.id
        assert job.spec_name == "persistence_test"
        assert job.csv_filename == "persist.csv"
        assert job.result_pass is True
        assert job.pdf_url == "/storage/test.pdf"
        assert job.evidence_url == "/storage/test.zip"
        assert job.metadata == {"key": "value"}
        assert job.status == "completed"


@pytest.mark.asyncio
async def test_quota_counter_increment(test_user):
    """Test quota counter increments correctly"""
    month_key = f"{datetime.now(timezone.utc).year:04d}-{datetime.now(timezone.utc).month:02d}"
    
    # Initially no counter
    async with get_db_session() as session:
        result = await session.execute(
            select(QuotaCounter).where(
                QuotaCounter.user_id == test_user.id,
                QuotaCounter.year_month == month_key
            )
        )
        counter = result.scalar_one_or_none()
        assert counter is None or counter.count == 0
    
    # Record a job
    await record_job(
        user_id=test_user.id,
        spec_name="counter_test",
        csv_filename="counter.csv",
        result_pass=True
    )
    
    # Counter should be created/incremented
    async with get_db_session() as session:
        result = await session.execute(
            select(QuotaCounter).where(
                QuotaCounter.user_id == test_user.id,
                QuotaCounter.year_month == month_key
            )
        )
        counter = result.scalar_one_or_none()
        assert counter is not None
        assert counter.count >= 1