from datetime import datetime, timezone
from typing import Optional
import uuid
from sqlalchemy import select
from ii_agent.db.models import LLMSetting
from ii_agent.server.api.deps import DBSession
from ii_agent.server.llm_settings.models import (
    ModelSettingCreate,
    ModelSettingUpdate,
    ModelSettingInfo,
    ModelSettingInfoWithKey,
    ModelSettingList,
    LLMModelInfo,
    LLMModelList,
)
from ii_agent.server.utils.encryption import encryption_manager
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.config.ii_agent_config import config


async def create_model_settings(
    *, db_session: DBSession, setting_model_in: ModelSettingCreate, user_id: str
) -> ModelSettingInfo:
    """Create or update model settings for a specific model."""

    # Check if settings already exist for this user and model
    existing_setting = (
        await db_session.execute(
            select(LLMSetting).filter(
                LLMSetting.user_id == user_id,
                LLMSetting.model == setting_model_in.model,
            )
        )
    ).scalar_one_or_none()

    encrypted_api_key = encryption_manager.encrypt(setting_model_in.api_key)

    if existing_setting:
        # Update existing settings
        existing_setting.api_type = setting_model_in.api_type.value
        existing_setting.encrypted_api_key = encrypted_api_key
        existing_setting.base_url = setting_model_in.base_url
        existing_setting.max_retries = setting_model_in.max_retries
        existing_setting.max_message_chars = setting_model_in.max_message_chars
        existing_setting.temperature = setting_model_in.temperature
        existing_setting.thinking_tokens = setting_model_in.thinking_tokens
        existing_setting.llm_metadata = setting_model_in.metadata
        existing_setting.updated_at = datetime.now(timezone.utc)

        await db_session.commit()
        await db_session.refresh(existing_setting)

        return _to_model_setting_info(existing_setting)
    else:
        # Create new settings
        new_setting = LLMSetting(
            id=str(uuid.uuid4()),
            user_id=user_id,
            model=setting_model_in.model,
            api_type=setting_model_in.api_type.value,
            encrypted_api_key=encrypted_api_key,
            base_url=setting_model_in.base_url,
            max_retries=setting_model_in.max_retries,
            max_message_chars=setting_model_in.max_message_chars,
            temperature=setting_model_in.temperature,
            thinking_tokens=setting_model_in.thinking_tokens,
            llm_metadata=setting_model_in.metadata,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db_session.add(new_setting)
        await db_session.commit()
        await db_session.refresh(new_setting)

        return _to_model_setting_info(new_setting)


async def update_model_settings(
    *,
    db_session: DBSession,
    model_id: str,
    setting_update: ModelSettingUpdate,
    user_id: str,
) -> Optional[ModelSettingInfo]:
    """Update existing model settings."""

    setting = (
        await db_session.execute(
            select(LLMSetting).filter(
                LLMSetting.id == model_id,
                LLMSetting.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if not setting:
        return None

    # Update only provided fields
    if setting_update.api_key is not None:
        setting.encrypted_api_key = encryption_manager.encrypt(setting_update.api_key)
    if setting_update.base_url is not None:
        setting.base_url = setting_update.base_url
    if setting_update.max_retries is not None:
        setting.max_retries = setting_update.max_retries
    if setting_update.max_message_chars is not None:
        setting.max_message_chars = setting_update.max_message_chars
    if setting_update.temperature is not None:
        setting.temperature = setting_update.temperature
    if setting_update.thinking_tokens is not None:
        setting.thinking_tokens = setting_update.thinking_tokens
    if setting_update.metadata is not None:
        setting.llm_metadata = setting_update.metadata
    if setting_update.is_active is not None:
        setting.is_active = setting_update.is_active

    setting.updated_at = datetime.now(timezone.utc)

    await db_session.commit()
    await db_session.refresh(setting)

    return _to_model_setting_info(setting)


async def get_model_settings(
    *, db_session: DBSession, model_id: str, user_id: str, include_key: bool = False
) -> Optional[ModelSettingInfoWithKey | ModelSettingInfo]:
    """Get model settings by ID."""

    setting = (
        await db_session.execute(
            select(LLMSetting).filter(
                LLMSetting.id == model_id,
                LLMSetting.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if not setting:
        return None

    if include_key:
        return _to_model_setting_info_with_key(setting)
    else:
        return _to_model_setting_info(setting)


async def get_model_settings_by_name(
    *, db_session: DBSession, model_name: str, user_id: str, include_key: bool = False
) -> Optional[ModelSettingInfoWithKey | ModelSettingInfo]:
    """Get model settings by model name."""

    setting = (
        await db_session.execute(
            select(LLMSetting).filter(
                LLMSetting.model == model_name,
                LLMSetting.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if not setting:
        return None

    if include_key:
        return _to_model_setting_info_with_key(setting)
    else:
        return _to_model_setting_info(setting)


async def list_model_settings(
    *, db_session: DBSession, user_id: str, api_type: Optional[str] = None
) -> ModelSettingList:
    """List all model settings for a user, optionally filtered by API type."""

    query = select(LLMSetting).filter(LLMSetting.user_id == user_id)

    if api_type:
        query = query.filter(LLMSetting.api_type == api_type)

    query = query.order_by(LLMSetting.created_at)

    settings = (await db_session.execute(query)).scalars().all()

    model_list = [_to_model_setting_info(setting) for setting in settings]

    return ModelSettingList(models=model_list)


async def delete_model_settings(
    *, db_session: DBSession, model_id: str, user_id: str
) -> bool:
    """Delete model settings by ID."""

    setting = (
        await db_session.execute(
            select(LLMSetting).filter(
                LLMSetting.id == model_id,
                LLMSetting.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if not setting:
        return False

    await db_session.delete(setting)
    await db_session.commit()

    return True


# Helper functions
def _to_model_setting_info(setting: LLMSetting) -> ModelSettingInfo:
    """Convert database model to Pydantic model."""
    return ModelSettingInfo(
        id=setting.id,
        model=setting.model,
        api_type=setting.api_type,
        base_url=setting.base_url,
        max_retries=setting.max_retries,
        max_message_chars=setting.max_message_chars,
        temperature=setting.temperature,
        thinking_tokens=setting.thinking_tokens if setting.thinking_tokens is not None else 16000,
        is_active=setting.is_active,
        has_api_key=bool(setting.encrypted_api_key),
        created_at=setting.created_at.isoformat() if setting.created_at else "",
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
        metadata=setting.llm_metadata or {},
    )


def _to_model_setting_info_with_key(setting: LLMSetting) -> ModelSettingInfoWithKey:
    """Convert database model to Pydantic model with decrypted API key."""
    return ModelSettingInfoWithKey(
        id=setting.id,
        model=setting.model,
        api_type=setting.api_type,
        base_url=setting.base_url,
        max_retries=setting.max_retries,
        max_message_chars=setting.max_message_chars,
        temperature=setting.temperature,
        thinking_tokens=setting.thinking_tokens if setting.thinking_tokens is not None else 16000,
        is_active=setting.is_active,
        has_api_key=bool(setting.encrypted_api_key),
        created_at=setting.created_at.isoformat() if setting.created_at else "",
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
        metadata=setting.llm_metadata or {},
        api_key=(
            encryption_manager.decrypt(setting.encrypted_api_key)
            if setting.encrypted_api_key
            else None
        ),
    )


def get_system_llm_config(*, model_id: str) -> LLMConfig:
    """
    Get LLM config from system configuration.

    Args:
        model_id: Name (id) of the model in system config

    Returns:
        LLMConfig: The system LLM configuration

    Raises:
        ValueError: If config not found
    """
    llm_config = config.llm_configs.get(model_id)
    if not llm_config:
        raise ValueError(f"LLM config not found for model: {model_id}")
    llm_config.setting_id = model_id
    llm_config.config_type = "system"
    return llm_config


async def get_user_llm_config(
    *, model_id: str, user_id: str, db_session: DBSession
) -> LLMConfig:
    """
    Get LLM config from user settings in database.

    Args:
        model_id: ID of the model in database
        user_id: User ID who owns the model settings
        db_session: Database session

    Returns:
        LLMConfig: The user LLM configuration

    Raises:
        ValueError: If config not found
    """
    llm_setting = await get_model_settings(
        db_session=db_session,
        model_id=model_id,
        user_id=user_id,
        include_key=True,
    )

    if not llm_setting:
        raise ValueError(f"LLM setting not found for model_id: {model_id}")

    return llm_setting.to_llm_config()


async def get_all_available_models(
    *, user_id: str, db_session: DBSession
) -> LLMModelList:
    """
    Get all available models from both system configs and user settings.

    Args:
        user_id: User ID to get user-configured models
        db_session: Database session

    Returns:
        LLMModelList: List of all available models
    """
    models = []

    # Get system models from config
    # TODO: check for subscription
    for model_id, llm_config in config.llm_configs.items():
        models.append(
            LLMModelInfo(
                id=model_id,
                model=llm_config.model,
                api_type=llm_config.api_type,
                source="system",
                description=f"System configured {model_id}",
            )
        )

    # Get user-configured models
    user_settings = await list_model_settings(db_session=db_session, user_id=user_id)

    for setting in user_settings.models:
        models.append(
            LLMModelInfo(
                id=setting.id,
                model=setting.model,
                api_type=setting.api_type,
                source="user",
                description=f"User configured {setting.model}",
            )
        )

    return LLMModelList(models=models)
