import base64
import json
import uuid
from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.features.diagram.models import Diagram

_logger = get_logger(__name__)


class DiagramService:
    async def create_diagram(
        self,
        db: AsyncSession,
        prompt: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> Diagram:
        """
        Create a diagram record, trigger LLM generation for Mermaid code,
        encode it to a mermaid.ink URL, persist, and return.
        """
        # 1. Create a pending diagram record
        diagram = Diagram(
            prompt=prompt,
            user_id=user_id,
            status="pending",
        )
        db.add(diagram)
        await db.flush()

        # 2. Generate Mermaid code using LiteLLM
        system_prompt = (
            "You are an expert software architect and system designer. "
            "Generate a syntactically correct, beautiful Mermaid.js diagram representing the system, architecture, or flow requested by the user.\n"
            "Guidelines:\n"
            "1. Return ONLY the raw Mermaid code block.\n"
            "2. Do NOT wrap it in markdown code blocks or code fences (e.g. do NOT include ```mermaid or ```).\n"
            "3. Do NOT include any explanations, warnings, or preamble.\n"
            "4. Use dark-friendly styles if applicable, but keep standard syntax.\n"
            "5. Start directly with the diagram type like: graph TD, sequenceDiagram, classDiagram, stateDiagram-v2, etc."
        )

        mermaid_code = ""
        try:
            llm = get_llm()
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ]
            response = await llm.ainvoke(messages)
            mermaid_code = response.content.strip()

            # Clean up the output in case LLM ignored rules and wrapped in code blocks
            if mermaid_code.startswith("```"):
                lines = mermaid_code.splitlines()
                # Remove starting fence line
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove ending fence line
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                mermaid_code = "\n".join(lines).strip()

        except Exception as exc:
            _logger.error("diagram_llm_generation_failed", error=str(exc))
            # Graceful fallback to a simple diagram in case of failure
            mermaid_code = (
                "graph TD\n"
                "  Start[Start Assessment] --> Error[LLM Generation Failed]\n"
                f"  Error --> Prompt[Prompt: {prompt[:30]}...]"
            )

        # 3. Base64-encode code for mermaid.ink
        try:
            state = {
                "code": mermaid_code,
                "mermaid": {"theme": "dark"},
            }
            json_bytes = json.dumps(state).encode("utf-8")
            base64_str = base64.b64encode(json_bytes).decode("utf-8")
            image_url = f"https://mermaid.ink/svg/{base64_str}"
            diagram.image_url = image_url
            diagram.status = "completed"
        except Exception as exc:
            _logger.error("diagram_base64_encoding_failed", error=str(exc))
            diagram.status = "failed"

        db.add(diagram)
        await db.flush()
        return diagram

    async def get_diagram(
        self,
        db: AsyncSession,
        diagram_id: uuid.UUID,
    ) -> Optional[Diagram]:
        """
        Retrieve a diagram record from the database by ID.
        """
        result = await db.exec(select(Diagram).where(Diagram.id == diagram_id))
        return result.first()

    async def list_user_diagrams(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[Diagram]:
        """
        Retrieve all diagrams generated for a specific user.
        """
        result = await db.exec(select(Diagram).where(Diagram.user_id == user_id))
        return list(result.all())