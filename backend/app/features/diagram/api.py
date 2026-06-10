import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.features.diagram.schemas import DiagramCreateRequest, DiagramResponse
from app.features.diagram.service import DiagramService

router = APIRouter(prefix="/diagram", tags=["Diagram"])
service = DiagramService()


@router.get("/health")
def diagram_health_check():
    return {
        "status": "ready",
        "feature": "diagram",
    }


@router.post("", response_model=DiagramResponse, status_code=status.HTTP_201_CREATED)
async def create_diagram(
    payload: DiagramCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a diagram dynamically and save it to the database.
    """
    return await service.create_diagram(
        db=db,
        prompt=payload.prompt,
        user_id=payload.user_id,
    )


@router.get("/{diagram_id}", response_model=DiagramResponse)
async def get_diagram(
    diagram_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a diagram by its UUID.
    """
    diagram = await service.get_diagram(db=db, diagram_id=diagram_id)
    if diagram is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagram not found",
        )
    return diagram


@router.get("/user/{user_id}", response_model=list[DiagramResponse])
async def list_user_diagrams(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    List all diagrams created by/for a specific user.
    """
    return await service.list_user_diagrams(db=db, user_id=user_id)