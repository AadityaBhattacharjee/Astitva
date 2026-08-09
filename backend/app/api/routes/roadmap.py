"""Roadmap and roadmap task CRUD routes for Phase 1."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.database.models.entities import Roadmap, RoadmapTask, User
from backend.app.database.schemas.roadmap import (
    RoadmapCreate,
    RoadmapRead,
    RoadmapTaskCreate,
    RoadmapTaskRead,
)
from backend.app.database.session import get_db

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


@router.get("/", response_model=list[RoadmapRead])
def list_roadmaps(db: Session = Depends(get_db)) -> list[Roadmap]:
    statement = select(Roadmap).options(selectinload(Roadmap.tasks)).order_by(Roadmap.id)
    return list(db.scalars(statement).all())


@router.post("/", response_model=RoadmapRead, status_code=status.HTTP_201_CREATED)
def create_roadmap(payload: RoadmapCreate, db: Session = Depends(get_db)) -> Roadmap:
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    roadmap = Roadmap(**payload.model_dump())
    db.add(roadmap)
    db.commit()
    db.refresh(roadmap)
    return db.scalar(select(Roadmap).options(selectinload(Roadmap.tasks)).where(Roadmap.id == roadmap.id)) or roadmap


@router.get("/tasks", response_model=list[RoadmapTaskRead])
def list_roadmap_tasks(db: Session = Depends(get_db)) -> list[RoadmapTask]:
    return list(db.scalars(select(RoadmapTask).order_by(RoadmapTask.id)).all())


@router.post("/tasks", response_model=RoadmapTaskRead, status_code=status.HTTP_201_CREATED)
def create_roadmap_task(payload: RoadmapTaskCreate, db: Session = Depends(get_db)) -> RoadmapTask:
    roadmap = db.get(Roadmap, payload.roadmap_id)
    if roadmap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found.")

    task = RoadmapTask(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
