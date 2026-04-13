"""Service layer for llm_settings domain - business logic only."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.secrets.encryption import encryption_manager
from ii_agent.settings.llm.exceptions import LLMSettingNotFoundError

if TYPE_CHECKING:
    from ii_agent.sessions.repository import SessionRepository
    from ii_agent.sessions.schemas import SessionInfo
from ii_agent.settings.llm.models import ModelSetting
from ii_agent.settings.llm.repository import ModelSettingRepository
from ii_agent.settings.llm.schemas import (
    ModelConfig,
    ModelParams,
    LLMModelInfo,
    LLMModelList,
    ModelSettingCreate,
    ModelSettingInfo,
    ModelSettingInfoWithKey,
    ModelSettingList,
    ModelSettingUpdate,
    PricingInfo,
)


class ModelSettingService:
    """Service for managing LLM settings - business logic layer."""

    def __init__(
        self,
        *,
        repo: ModelSettingRepository,
        session_repo: SessionRepository,
    ) -> None:
        self._repo = repo
        self._session_repo = session_repo

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_model_settings(
        self,
        db: AsyncSession,
        *,
        model_setting_request: ModelSettingCreate,
        user_id: uuid.UUID,
    ) -> ModelSettingInfo:
        """Create or upsert model settings for a specific model."""
        existing = await self._repo.find_by_model_and_user(
            db, model_setting_request.model_id, user_id=user_id
        )

        encrypted_api_key = encryption_manager.encrypt(model_setting_request.api_key)
        configs_dict = (
            model_setting_request.configs.model_dump(exclude_none=True)
            if model_setting_request.configs
            else None
        )
        pricing_dict = (
            model_setting_request.pricing.model_dump() if model_setting_request.pricing else None
        )

        if existing:
            existing.provider = model_setting_request.provider
            existing.encrypted_api_key = encrypted_api_key
            existing.base_url = model_setting_request.base_url
            existing.display_name = model_setting_request.display_name
            existing.params = configs_dict
            existing.pricing = pricing_dict
            existing.config_type = model_setting_request.config_type
            existing.is_default = model_setting_request.is_default
            existing.is_active = model_setting_request.is_active
            existing.updated_at = datetime.now(timezone.utc)

            updated = await self._repo.update(db, existing)
            return _to_model_setting_info(updated)

        new_setting = ModelSetting(
            user_id=user_id,
            model_id=model_setting_request.model_id,
            provider=model_setting_request.provider,
            encrypted_api_key=encrypted_api_key,
            base_url=model_setting_request.base_url,
            display_name=model_setting_request.display_name,
            params=configs_dict,
            pricing=pricing_dict,
            config_type=model_setting_request.config_type,
            is_default=model_setting_request.is_default,
            is_active=model_setting_request.is_active,
        )

        created = await self._repo.create(db, new_setting)
        return _to_model_setting_info(created)

    async def update_model_settings(
        self,
        db: AsyncSession,
        *,
        setting_id: uuid.UUID,
        setting_update: ModelSettingUpdate,
        user_id: uuid.UUID,
    ) -> ModelSettingInfo:
        """Update existing model settings.

        Raises:
            LLMSettingNotFoundError: If setting not found or access denied.
        """
        setting = await self._repo.find_by_id_and_user_id(db, setting_id, user_id)
        if not setting:
            raise LLMSettingNotFoundError(f"Model setting {setting_id} not found or access denied")

        if setting_update.api_key is not None:
            setting.encrypted_api_key = encryption_manager.encrypt(setting_update.api_key)
        if setting_update.base_url is not None:
            setting.base_url = setting_update.base_url
        if setting_update.display_name is not None:
            setting.display_name = setting_update.display_name
        if setting_update.configs is not None:
            setting.params = setting_update.configs.model_dump(exclude_none=True)
        if setting_update.pricing is not None:
            setting.pricing = setting_update.pricing.model_dump()
        if setting_update.config_type is not None:
            setting.config_type = setting_update.config_type
        if setting_update.is_default is not None:
            setting.is_default = setting_update.is_default
        if setting_update.is_active is not None:
            setting.is_active = setting_update.is_active

        setting.updated_at = datetime.now(timezone.utc)
        updated = await self._repo.update(db, setting)
        return _to_model_setting_info(updated)

    async def get_model_settings(
        self,
        db: AsyncSession,
        *,
        setting_id: uuid.UUID,
        user_id: uuid.UUID,
        include_key: bool = False,
    ) -> ModelSettingInfoWithKey | ModelSettingInfo | None:
        """Get model settings by ID."""
        setting = await self._repo.find_by_id_and_user_id(db, setting_id, user_id)
        if not setting:
            return None

        return _to_model_setting_info(setting, include_key=include_key)

    async def get_model_settings_by_name(
        self,
        db: AsyncSession,
        *,
        model_name: str,
        user_id: uuid.UUID,
        include_key: bool = False,
    ) -> ModelSettingInfoWithKey | ModelSettingInfo | None:
        """Get model settings by model_id string."""
        setting = await self._repo.find_by_model_and_user(db, model_name, user_id)
        if not setting:
            return None

        return _to_model_setting_info(setting, include_key=include_key)

    async def list_model_settings(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        provider: str | None = None,
    ) -> ModelSettingList:
        """List all model settings for a user."""
        settings = await self._repo.find_all_by_user(db, user_id, provider=provider)
        model_list = [_to_model_setting_info(s) for s in settings]
        return ModelSettingList(models=model_list)

    async def delete_model_settings(
        self,
        db: AsyncSession,
        *,
        model_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Delete model settings by ID."""
        setting = await self._repo.find_by_id_and_user_id(db, model_id, user_id)
        if not setting:
            return False

        await self._repo.delete(db, setting)
        return True

    # ------------------------------------------------------------------
    # Aggregation / resolution
    # ------------------------------------------------------------------

    async def get_all_available_models(
        self, db: AsyncSession, *, user_id: uuid.UUID
    ) -> LLMModelList:
        """Get all available models from DB (system + user settings).

        The database is the single source of truth. System models are seeded
        from ``MODEL_CONFIGS`` env var at startup via ``seed_admin_llm_settings``.
        """
        models: list[LLMModelInfo] = []

        # 1. System rows from DB (user_id IS NULL, config_type='system')
        system_rows = await self._repo.find_all_system_models(db)
        for row in system_rows:
            pricing = PricingInfo.model_validate(row.pricing) if row.pricing else None
            models.append(
                LLMModelInfo(
                    id=row.id,
                    model_id=row.model_id,
                    model=row.model_id,
                    provider=row.provider,
                    source=row.config_type,
                    display_name=row.display_name or row.model_id,
                    base_url=row.base_url,
                    pricing=pricing,
                )
            )

        # 2. User settings
        user_settings = await self.list_model_settings(db, user_id=user_id)

        for setting in user_settings.models:
            models.append(
                LLMModelInfo(
                    id=setting.id,
                    model_id=setting.model_id,
                    model=setting.model_id,
                    provider=setting.provider,
                    source=setting.config_type,
                    display_name=setting.display_name or setting.model_id,
                    base_url=setting.base_url,
                    pricing=setting.pricing,
                )
            )

        return LLMModelList(models=models)

    async def get_user_model_config(
        self,
        db: AsyncSession,
        *,
        setting_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ModelConfig:
        """Get model config from user settings in database.

        Raises:
            ValueError: If config not found.
        """
        setting = await self._repo.find_by_id_and_user_id(db, setting_id, user_id)
        if not setting:
            raise ValueError(f"Model setting not found: {setting_id}")
        return _setting_to_model_config(setting)

    async def resolve_system_config(self, db: AsyncSession, *, model_id: str) -> ModelConfig:
        """Resolve a system model config from DB by model_id.

        Raises:
            ValueError: If no system setting found for the given model_id.
        """
        setting = await self._repo.find_system_model_by_model_id(db, model_id)
        if not setting:
            raise ValueError(f"System model config not found for model: {model_id}")
        return _setting_to_model_config(setting)

    async def resolve_config_by_setting_id(
        self, db: AsyncSession, *, setting_id: uuid.UUID
    ) -> ModelConfig:
        """Resolve a model config by its model_settings.id (user or system).

        Raises:
            ValueError: If no setting found for the given id.
        """
        setting = await self._repo.get_by_id(db, setting_id)
        if not setting:
            raise ValueError(f"Model setting not found: {setting_id}")
        return _setting_to_model_config(setting)

    async def resolve_model_config(
        self,
        db: AsyncSession,
        *,
        session: SessionInfo,
        source: str | None = None,
        model_id: str | None = None,
    ) -> ModelConfig:
        """Resolve the model config for an agent run.

        Looks up the session's ``model_setting_id`` and resolves to either
        a user or system config.

        Raises:
            ValueError: If no matching config can be found.
        """
        current_session = await self._session_repo.get_by_id(db, session.id)
        model_setting_id = current_session.model_setting_id if current_session else None

        if model_setting_id is None:
            if source == "user" and model_id:
                return await self.get_user_model_config(
                    db,
                    setting_id=uuid.UUID(model_id),
                    user_id=session.user_id,
                )
            if not model_id:
                raise ValueError("model_id is required when session has no model_setting_id")
            return await self.resolve_system_config(db, model_id=model_id)

        try:
            return await self.get_user_model_config(
                db,
                setting_id=model_setting_id,
                user_id=session.user_id,
            )
        except (ValueError, AttributeError):
            return await self.resolve_config_by_setting_id(db, setting_id=model_setting_id)


# ---------------------------------------------------------------------------
# Standalone async helpers (DB-based)
# ---------------------------------------------------------------------------


async def get_system_model_config_from_db(db: AsyncSession, *, model_id: str) -> ModelConfig:
    """Get system model config from the database.

    Standalone helper for code outside the service (e.g., tool constructors).

    Raises:
        ValueError: If no system setting found for the given model_id.
    """
    repo = ModelSettingRepository()
    setting = await repo.find_system_model_by_model_id(db, model_id)
    if not setting:
        raise ValueError(f"System model config not found for model: {model_id}")
    return _setting_to_model_config(setting)


def _setting_to_model_config(setting: ModelSetting) -> ModelConfig:
    """Convert a DB ``ModelSetting`` row to a ``ModelConfig`` value object."""
    params = ModelParams.model_validate(setting.params) if setting.params else ModelParams()
    pricing = PricingInfo.model_validate(setting.pricing) if setting.pricing else None

    api_key: SecretStr | None = None
    if setting.encrypted_api_key:
        api_key = SecretStr(encryption_manager.decrypt(setting.encrypted_api_key))

    return ModelConfig(
        id=setting.id,
        model_id=setting.model_id,
        provider=setting.provider,
        api_key=api_key,
        base_url=setting.base_url,
        display_name=setting.display_name,
        params=params,
        pricing=pricing,
        config_type=setting.config_type,
    )


def _to_model_setting_info(
    setting: ModelSetting, *, include_key: bool = False
) -> ModelSettingInfoWithKey | ModelSettingInfo:
    """Convert database model to Pydantic model."""
    configs = ModelParams.model_validate(setting.params) if setting.params else None
    pricing = PricingInfo.model_validate(setting.pricing) if setting.pricing else None

    shared = dict(
        id=setting.id,
        model_id=setting.model_id,
        provider=setting.provider,
        base_url=setting.base_url,
        display_name=setting.display_name,
        configs=configs,
        pricing=pricing,
        config_type=setting.config_type,
        is_default=setting.is_default,
        is_active=setting.is_active,
        has_api_key=bool(setting.encrypted_api_key),
        created_at=setting.created_at.isoformat() if setting.created_at else "",
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
    )

    if include_key:
        return ModelSettingInfoWithKey(
            **shared,
            api_key=(
                encryption_manager.decrypt(setting.encrypted_api_key)
                if setting.encrypted_api_key
                else None
            ),
        )

    return ModelSettingInfo(**shared)
