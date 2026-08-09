"""Authenticated roadmap lifecycle routes."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.database.models.entities import User
from backend.app.database.schemas.roadmap import (
    RoadmapGenerateRequest,
    RoadmapStatusRead,
    TaskGuideChatRequest,
    TaskGuideChatResponse,
    TaskGuideRead,
    RoadmapTaskUpdate,
)
from backend.app.database.session import get_db
from backend.app.services.llm_provider import get_llm_provider
from backend.app.services.roadmap_service import (
    RoadmapService,
    RoadmapUnavailableError,
    RoadmapValidationError,
)
from backend.app.services.task_guide_service import TaskGuideService

router = APIRouter(prefix="/roadmaps", tags=["roadmaps"])


def _service(db: Session) -> RoadmapService:
    return RoadmapService(db=db, llm_provider=get_llm_provider())


def _guide_service(db: Session) -> TaskGuideService:
    return TaskGuideService(db=db, llm_provider=get_llm_provider())


@router.get("/me", response_model=RoadmapStatusRead)
def get_my_roadmap(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapStatusRead:
    service = _service(db)
    roadmap = service.get_current_roadmap(current_user.id)
    if roadmap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found.")
    progress = service.get_or_create_progress(roadmap)
    db.commit()
    db.refresh(progress)
    return RoadmapStatusRead(roadmap=roadmap, progress=progress, created=False)


@router.post("/generate", response_model=RoadmapStatusRead, status_code=status.HTTP_201_CREATED)
def generate_my_roadmap(
    payload: RoadmapGenerateRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapStatusRead:
    service = _service(db)
    try:
        result = service.generate_for_user(current_user, force_refresh=payload.force_refresh)
    except RoadmapValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RoadmapUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return RoadmapStatusRead(
        roadmap=result.roadmap,
        progress=result.progress,
        created=result.created,
    )


@router.patch("/tasks/{task_id}", response_model=RoadmapStatusRead)
def update_my_task(
    task_id: int,
    payload: RoadmapTaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapStatusRead:
    service = _service(db)
    try:
        result = service.update_task_status(current_user.id, task_id, payload.status)
    except RoadmapValidationError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if detail == "Task not found." else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=detail) from exc
    except RoadmapUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return RoadmapStatusRead(
        roadmap=result.roadmap,
        progress=result.progress,
        created=False,
    )


@router.get("/tasks/{task_id}/guide", response_model=TaskGuideRead)
def get_task_guide(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskGuideRead:
    service = _guide_service(db)
    try:
        return TaskGuideRead(**service.build_initial_guide(current_user.id, task_id))
    except RoadmapValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/guide/chat", response_model=TaskGuideChatResponse)
def task_guide_chat(
    task_id: int,
    payload: TaskGuideChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskGuideChatResponse:
    service = _guide_service(db)
    try:
        return TaskGuideChatResponse(**service.answer_follow_up(current_user.id, task_id, payload.query))
    except RoadmapValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
