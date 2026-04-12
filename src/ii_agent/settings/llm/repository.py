"""Repository layer for llm_settings domain - data access only."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.settings.llm.models import ModelSetting


class ModelSettingRepository(BaseRepository[ModelSetting]):
    """Data access layer for LLMSetting model."""

    model = ModelSetting

    async def find_by_id_and_user_id(
        self, db: AsyncSession, setting_id: uuid.UUID, user_id: uuid.UUID
    ) -> ModelSetting | None:
        """Get an LLM setting by ID for a specific user."""
        result = await db.execute(
            select(ModelSetting).where(
                ModelSetting.id == setting_id,
                ModelSetting.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_by_model_and_user(
        self, db: AsyncSession, model_id: str, user_id: uuid.UUID
    ) -> ModelSetting | None:
        """Get an LLM setting by model_id for a specific user."""
        result = await db.execute(
            select(ModelSetting).where(
                ModelSetting.model_id == model_id,
                ModelSetting.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_all_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        provider: str | None = None,
        config_type: str | None = None,
    ) -> list[ModelSetting]:
        """List all LLM settings for a user, optionally filtered."""
        query = select(ModelSetting).where(ModelSetting.user_id == user_id)

        if provider:
            query = query.where(ModelSetting.provider == provider)
        if config_type:
            query = query.where(ModelSetting.config_type == config_type)

        query = query.order_by(ModelSetting.created_at)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def find_all_system_models(self, db: AsyncSession) -> list[ModelSetting]:
        """List all system-level LLM settings (user_id is NULL)."""
        query = (
            select(ModelSetting)
            .where(
                ModelSetting.user_id.is_(None),
                ModelSetting.config_type == "system",
            )
            .order_by(ModelSetting.created_at)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def find_system_model_by_model_id(
        self, db: AsyncSession, model_id: str
    ) -> ModelSetting | None:
        """Get a system-level setting by model_id."""
        result = await db.execute(
            select(ModelSetting).where(
                ModelSetting.model_id == model_id,
                ModelSetting.user_id.is_(None),
                ModelSetting.config_type == "system",
            )
        )
        return result.scalars().first()

    async def find_system_model_by_provider(
        self, db: AsyncSession, provider: str
    ) -> ModelSetting | None:
        """Get a system-level setting by model_id."""
        result = await db.execute(
            select(ModelSetting).where(
                ModelSetting.provider == provider,
                ModelSetting.user_id.is_(None),
                ModelSetting.config_type == "system",
            )
        )
        return result.scalars().first()

    async def delete(self, db: AsyncSession, setting: ModelSetting) -> None:
        """Delete an LLM setting."""
        await db.delete(setting)
        await db.flush()
