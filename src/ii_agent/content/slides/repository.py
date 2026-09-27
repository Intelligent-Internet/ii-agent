"""Repository layer for slides domain - data access only.

Operates on SlideContent model which stores individual slide content
for presentations within sessions.
"""

from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.content.slides.models import SlideContent


class SlideContentRepository(BaseRepository[SlideContent]):
    """Data access layer for SlideContent model.

    Inherits from BaseRepository: get_by_id, save, update.
    """

    model = SlideContent

    async def get_by_session_and_presentation_and_number(
        self,
        db: AsyncSession,
        session_id: str,
        presentation_name: str,
        slide_number: int,
    ) -> Optional[SlideContent]:
        """Get a specific slide by session, presentation, and number."""
        result = await db.execute(
            select(SlideContent).where(
                and_(
                    SlideContent.session_id == session_id,
                    SlideContent.presentation_name == presentation_name,
                    SlideContent.slide_number == slide_number,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_presentations_summary(self, db: AsyncSession, session_id: str) -> List:
        """Get presentation summary (name, count, last_updated) for a session."""
        result = await db.execute(
            select(
                SlideContent.presentation_name,
                func.count(SlideContent.id).label("slide_count"),
                func.max(SlideContent.updated_at).label("last_updated"),
            )
            .where(SlideContent.session_id == session_id)
            .group_by(SlideContent.presentation_name)
            .order_by(func.max(SlideContent.updated_at).desc())
        )
        return list(result)

    async def get_slides_by_session_and_presentation(
        self,
        db: AsyncSession,
        session_id: str,
        presentation_name: str,
    ) -> List[SlideContent]:
        """Get all slides for a specific presentation in a session."""
        result = await db.execute(
            select(SlideContent)
            .where(
                and_(
                    SlideContent.session_id == session_id,
                    SlideContent.presentation_name == presentation_name,
                )
            )
            .order_by(SlideContent.slide_number)
        )
        return list(result.scalars().all())

    async def get_slides_by_session(
        self,
        db: AsyncSession,
        session_id: str,
        presentation_name: Optional[str] = None,
    ) -> List[SlideContent]:
        """Get all slides for a session, optionally filtered by presentation."""
        query = select(SlideContent).where(SlideContent.session_id == session_id)

        if presentation_name:
            query = query.where(SlideContent.presentation_name == presentation_name)

        query = query.order_by(SlideContent.presentation_name, SlideContent.slide_number)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def upsert_slide(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: str,
        slide_number: int,
        slide_title: str,
        slide_content: str,
        tool_name: str,
    ) -> str:
        """Create or update a slide. Returns the slide ID."""
        existing_slide = await self.get_by_session_and_presentation_and_number(
            db,
            session_id=session_id,
            presentation_name=presentation_name,
            slide_number=slide_number,
        )

        now = datetime.now(timezone.utc)
        metadata = {
            "tool_name": tool_name,
            "last_tool_execution": now.isoformat(),
        }

        if existing_slide:
            existing_slide.slide_title = slide_title
            existing_slide.slide_content = slide_content
            existing_slide.slide_metadata = metadata
            existing_slide.updated_at = now
            await db.flush()
            return existing_slide.id
        else:
            new_slide = SlideContent(
                session_id=session_id,
                presentation_name=presentation_name,
                slide_number=slide_number,
                slide_title=slide_title,
                slide_content=slide_content,
                slide_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            db.add(new_slide)
            await db.flush()
            return new_slide.id
