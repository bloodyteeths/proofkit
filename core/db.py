"""
Database connection and session management

Provides async PostgreSQL connection with SQLModel
Configured via DATABASE_URL environment variable
"""

import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel


# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"

# Convert postgresql:// to postgresql+asyncpg:// for async support
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=DB_ECHO,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before using
    # Use NullPool for pgbouncer compatibility
    poolclass=NullPool if os.getenv("USE_PGBOUNCER", "false").lower() == "true" else None
)

# Create async session maker
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes to get database session
    
    Usage:
        @app.get("/users")
        async def get_users(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(User))
            return result.scalars().all()
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for getting database session outside of FastAPI
    
    Usage:
        async with get_db_session() as session:
            user = await session.get(User, user_id)
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Initialize database tables
    Should only be called once during app startup
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db():
    """
    Close database connections
    Should be called during app shutdown
    """
    await engine.dispose()


async def get_recent_jobs(user_email: str, limit: int = 10) -> list[dict]:
    """
    Get recent jobs for a user from database or file storage.
    
    Args:
        user_email: Email address of the user
        limit: Maximum number of jobs to return
        
    Returns:
        List of recent job dictionaries with pass_bool and pdf_url fields
        
    Example:
        jobs = await get_recent_jobs('user@example.com', 5)
        for job in jobs:
            print(f"Job {job['id']}: {'PASS' if job['pass_bool'] else 'FAIL'}")
    """
    try:
        # If we have database connection, use SQLModel query
        if DATABASE_URL:
            from core.models_sql import Job, User as SQLUser
            from sqlalchemy import select, desc
            
            async with get_db_session() as session:
                # First get the user ID
                user_stmt = select(SQLUser).where(SQLUser.email == user_email)
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                
                if not user:
                    return []
                
                # Get recent jobs for this user
                jobs_stmt = (
                    select(Job)
                    .where(Job.user_id == user.id)
                    .order_by(desc(Job.created_at))
                    .limit(limit)
                )
                
                jobs_result = await session.execute(jobs_stmt)
                jobs = jobs_result.scalars().all()
                
                # Convert to dictionaries
                job_list = []
                for job in jobs:
                    job_dict = {
                        "id": str(job.id),
                        "spec_name": job.spec_name,
                        "csv_filename": job.csv_filename,
                        "pass_bool": job.result_pass,
                        "pdf_url": job.pdf_url,
                        "evidence_url": job.evidence_url,
                        "status": job.status,
                        "created_at": job.created_at.isoformat(),
                        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                        "error_message": job.error_message,
                        "metadata": job.metadata
                    }
                    job_list.append(job_dict)
                
                return job_list
        
        else:
            # Fallback to file-based storage for development/testing
            return _get_recent_jobs_from_files(user_email, limit)
            
    except Exception as e:
        from core.logging import get_logger
        logger = get_logger(__name__)
        logger.error(f"Error getting recent jobs for {user_email}: {e}")
        
        # Fallback to file-based approach
        return _get_recent_jobs_from_files(user_email, limit)


def _get_recent_jobs_from_files(user_email: str, limit: int = 10) -> list[dict]:
    """
    Fallback method to get recent jobs from file storage.
    
    Args:
        user_email: Email address of the user
        limit: Maximum number of jobs to return
        
    Returns:
        List of recent job dictionaries
    """
    import hashlib
    import json
    from pathlib import Path
    from datetime import datetime, timezone
    
    try:
        # Hash email for privacy
        email_hash = hashlib.sha256(user_email.encode()).hexdigest()[:16]
        storage_dir = Path("storage") / email_hash
        
        if not storage_dir.exists():
            return []
        
        jobs = []
        
        # Look for job directories (format: YYYY-MM-DD_HHMMSS_jobid)
        for job_dir in sorted(storage_dir.glob("*"), reverse=True):
            if not job_dir.is_dir():
                continue
            
            # Try to parse job data
            decision_file = job_dir / "decision.json"
            manifest_file = job_dir / "manifest.txt"
            pdf_file = None
            
            # Find PDF file
            for pdf in job_dir.glob("*.pdf"):
                pdf_file = pdf
                break
            
            if decision_file.exists():
                try:
                    with open(decision_file, 'r') as f:
                        decision_data = json.load(f)
                    
                    # Parse job directory name for timestamp
                    dir_parts = job_dir.name.split('_')
                    if len(dir_parts) >= 2:
                        date_str = dir_parts[0]
                        time_str = dir_parts[1]
                        created_at = datetime.strptime(
                            f"{date_str}_{time_str}", 
                            "%Y-%m-%d_%H%M%S"
                        ).replace(tzinfo=timezone.utc)
                    else:
                        created_at = datetime.fromtimestamp(
                            job_dir.stat().st_ctime, 
                            tz=timezone.utc
                        )
                    
                    job_dict = {
                        "id": job_dir.name,
                        "spec_name": decision_data.get("spec", {}).get("name", "Unknown"),
                        "csv_filename": decision_data.get("csv_metadata", {}).get("filename", "data.csv"),
                        "pass_bool": decision_data.get("result", {}).get("overall", {}).get("pass", False),
                        "pdf_url": f"/download/{email_hash}/{job_dir.name}/certificate.pdf" if pdf_file else None,
                        "evidence_url": f"/download/{email_hash}/{job_dir.name}/evidence.zip" if manifest_file.exists() else None,
                        "status": "completed",
                        "created_at": created_at.isoformat(),
                        "completed_at": created_at.isoformat(),
                        "error_message": None,
                        "metadata": {
                            "temperature_range": decision_data.get("result", {}).get("temperature_range"),
                            "duration_minutes": decision_data.get("result", {}).get("duration_minutes"),
                            "hold_time_minutes": decision_data.get("result", {}).get("continuous_hold", {}).get("duration_minutes")
                        }
                    }
                    
                    jobs.append(job_dict)
                    
                    if len(jobs) >= limit:
                        break
                        
                except Exception as e:
                    # Skip jobs with parsing errors
                    continue
        
        return jobs
        
    except Exception as e:
        from core.logging import get_logger
        logger = get_logger(__name__)
        logger.error(f"Error getting jobs from files for {user_email}: {e}")
        return []