import pytest
from sqlalchemy import delete
from sqlmodel import select

from app.core.database import SQLModel, async_session, engine
from app.features.diagram.models import Diagram
from app.features.diagram.service import DiagramService
from app.features.diagram.tool import (
    generate_diagram_for_agent_async,
    get_diagram_tools,
)

service = DiagramService()


async def reset_diagram_tables():
    """
    Create diagram tables if needed and clean diagram data before each database test.
    """
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    async with async_session() as db:
        await db.exec(delete(Diagram))
        await db.commit()

    await engine.dispose()


@pytest.fixture
async def db_session():
    await reset_diagram_tables()

    async with async_session() as db:
        try:
            yield db
        finally:
            await db.rollback()
            await db.close()
            await engine.dispose()


@pytest.mark.asyncio
async def test_diagram_creation_and_persistence(db_session):
    """
    Test that calling create_diagram generates a record and stores it in the database.
    """
    prompt_text = "Draw a simple flowchart showing client connecting to API."
    diagram = await service.create_diagram(
        db=db_session,
        prompt=prompt_text,
        user_id=None,
    )
    await db_session.commit()

    assert diagram.id is not None
    assert diagram.prompt == prompt_text
    assert diagram.status == "completed"
    assert diagram.image_url is not None
    assert diagram.image_url.startswith("https://mermaid.ink/svg/")

    saved_result = await db_session.exec(select(Diagram).where(Diagram.id == diagram.id))
    saved_diagram = saved_result.first()

    assert saved_diagram is not None
    assert saved_diagram.prompt == prompt_text
    assert saved_diagram.status == "completed"
    assert saved_diagram.image_url == diagram.image_url


@pytest.mark.asyncio
async def test_diagram_retrieval_and_listing(db_session):
    """
    Test diagram retrieval by ID and listing by user ID.
    """
    import uuid

    user_id = uuid.uuid4()
    prompt_text = "Database schema architecture"

    d1 = await service.create_diagram(db=db_session, prompt=prompt_text, user_id=user_id)
    await db_session.commit()

    retrieved = await service.get_diagram(db=db_session, diagram_id=d1.id)
    assert retrieved is not None
    assert retrieved.prompt == prompt_text
    assert retrieved.user_id == user_id

    user_diagrams = await service.list_user_diagrams(db=db_session, user_id=user_id)
    assert len(user_diagrams) == 1
    assert user_diagrams[0].id == d1.id


@pytest.mark.asyncio
async def test_diagram_agent_tool_contract():
    """
    Test that the LangChain tool exposes correct structure and contract.
    """
    await reset_diagram_tables()

    tools = get_diagram_tools()
    assert len(tools) == 1

    tool = tools[0]
    assert tool.name == "diagram_generate_visualization"
    assert tool.description is not None
    assert tool.args_schema is not None

    fields = tool.args_schema.model_fields
    assert "prompt" in fields
    assert "user_id" in fields

    result = await generate_diagram_for_agent_async(
        prompt="Three-tier web application architecture",
        user_id=None,
    )
    assert result["id"] is not None
    assert result["prompt"] == "Three-tier web application architecture"
    assert result["status"] == "completed"
    assert result["image_url"].startswith("https://mermaid.ink/svg/")

    await engine.dispose()
