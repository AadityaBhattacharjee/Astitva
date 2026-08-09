"""Authenticated progress routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.database.models.entities import User
from backend.app.database.schemas.roadmap import ProgressRead
from backend.app.database.session import get_db
from backend.app.services.llm_provider import get_llm_provider
from backend.app.services.roadmap_service import RoadmapService

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/me", response_model=ProgressRead)
def get_my_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressRead:
    service = RoadmapService(db=db, llm_provider=get_llm_provider())
    roadmap = service.get_current_roadmap(current_user.id)
    if roadmap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Progress not found.")
    progress = service.get_or_create_progress(roadmap)
    db.commit()
    db.refresh(progress)
    return progress
