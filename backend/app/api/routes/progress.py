"""Progress CRUD routes for Phase 1."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.models.entities import Progress, Roadmap
from backend.app.database.schemas.roadmap import ProgressCreate, ProgressRead
from backend.app.database.session import get_db

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/", response_model=list[ProgressRead])
def list_progress(db: Session = Depends(get_db)) -> list[Progress]:
    return list(db.scalars(select(Progress).order_by(Progress.id)).all())


@router.post("/", response_model=ProgressRead, status_code=status.HTTP_201_CREATED)
def create_progress(payload: ProgressCreate, db: Session = Depends(get_db)) -> Progress:
    roadmap = db.get(Roadmap, payload.roadmap_id)
    if roadmap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found.")

    progress = Progress(**payload.model_dump())
    db.add(progress)
    db.commit()
    db.refresh(progress)
    return progress
