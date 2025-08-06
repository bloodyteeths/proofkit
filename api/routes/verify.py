"""
Verify API route - loads jobs from database

Allows users to re-verify certificates and view job history
"""

from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_session
from quota.postgres import get_job_by_id, get_recent_jobs
from auth.magic import verify_session_token
from typing import Optional

router = APIRouter(prefix="/api/verify", tags=["verify"])


async def get_current_user(authorization: Optional[str] = None):
    """Get current user from session token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    token = authorization.replace("Bearer ", "")
    user = await verify_session_token(token)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return user


@router.get("/job/{job_id}")
async def get_job(
    job_id: UUID,
    current_user=Depends(get_current_user)
):
    """
    Get job details by ID
    Returns 404 if job not found or doesn't belong to user
    """
    job = await get_job_by_id(job_id, user_id=current_user.id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "id": str(job.id),
        "status": job.status,
        "spec_name": job.spec_name,
        "csv_filename": job.csv_filename,
        "result_pass": job.result_pass,
        "pdf_url": job.pdf_url,
        "evidence_url": job.evidence_url,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "metadata": job.metadata
    }


@router.get("/jobs")
async def list_jobs(
    limit: int = 20,
    current_user=Depends(get_current_user)
):
    """
    List user's recent jobs
    """
    if limit > 100:
        limit = 100
    
    jobs = await get_recent_jobs(current_user.id, limit=limit)
    
    return {
        "jobs": [
            {
                "id": str(job.id),
                "status": job.status,
                "spec_name": job.spec_name,
                "csv_filename": job.csv_filename,
                "result_pass": job.result_pass,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            }
            for job in jobs
        ],
        "total": len(jobs)
    }


@router.get("/job/{job_id}/pdf")
async def download_pdf(
    job_id: UUID,
    current_user=Depends(get_current_user)
):
    """
    Download PDF for a job
    """
    job = await get_job_by_id(job_id, user_id=current_user.id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job.pdf_url:
        raise HTTPException(status_code=404, detail="PDF not available")
    
    # If PDF is stored locally
    if job.pdf_url.startswith("/storage/"):
        file_path = job.pdf_url.replace("/storage/", "storage/")
        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=f"certificate_{job.id}.pdf"
        )
    
    # If PDF is stored in S3, redirect
    return JSONResponse(
        status_code=302,
        headers={"Location": job.pdf_url}
    )


@router.get("/job/{job_id}/evidence")
async def download_evidence(
    job_id: UUID,
    current_user=Depends(get_current_user)
):
    """
    Download evidence ZIP for a job
    """
    job = await get_job_by_id(job_id, user_id=current_user.id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job.evidence_url:
        raise HTTPException(status_code=404, detail="Evidence not available")
    
    # If evidence is stored locally
    if job.evidence_url.startswith("/storage/"):
        file_path = job.evidence_url.replace("/storage/", "storage/")
        return FileResponse(
            path=file_path,
            media_type="application/zip",
            filename=f"evidence_{job.id}.zip"
        )
    
    # If evidence is stored in S3, redirect
    return JSONResponse(
        status_code=302,
        headers={"Location": job.evidence_url}
    )


@router.post("/job/{job_id}/reverify")
async def reverify_job(
    job_id: UUID,
    current_user=Depends(get_current_user)
):
    """
    Re-verify a job (re-run the verification process)
    """
    job = await get_job_by_id(job_id, user_id=current_user.id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # TODO: Implement re-verification logic
    # This would re-run the CSV processing with the same spec
    
    return {
        "message": "Re-verification not yet implemented",
        "job_id": str(job_id)
    }