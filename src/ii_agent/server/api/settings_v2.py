"""Enhanced settings management API endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ii_agent.db.manager import get_db
from ii_agent.db.models import User, LLMSetting, MCPSetting
from ii_agent.server.auth.middleware import get_current_user
from ii_agent.server.models.settings import (
    LLMProviderCreate,
    LLMProviderUpdate,
    LLMProviderInfo,
    LLMProviderList,
    MCPConfigCreate,
    MCPConfigUpdate,
    MCPConfigInfo,
    MCPConfigList,
    ProviderValidation,
    APIKeyTest,
    SettingsExport,
)
from ii_agent.server.utils.encryption import encryption_manager


router = APIRouter(prefix="/v2/settings", tags=["Enhanced Settings Management"])


@router.get("/llm-providers", response_model=LLMProviderList)
async def list_llm_providers(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List user's LLM provider settings."""

    providers = (
        db.query(LLMSetting)
        .filter(LLMSetting.user_id == current_user.id)
        .order_by(LLMSetting.created_at)
        .all()
    )

    provider_list = [
        LLMProviderInfo(
            id=provider.id,
            provider=provider.provider,
            base_url=provider.base_url,
            is_active=provider.is_active,
            has_api_key=bool(provider.encrypted_api_key),
            created_at=provider.created_at.isoformat() if provider.created_at else "",
            updated_at=provider.updated_at.isoformat() if provider.updated_at else None,
            metadata=provider.metadata,
        )
        for provider in providers
    ]

    return LLMProviderList(providers=provider_list)


@router.post(
    "/llm-providers",
    response_model=LLMProviderInfo,
    status_code=status.HTTP_201_CREATED,
)
async def create_llm_provider(
    provider_data: LLMProviderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new LLM provider setting."""

    # Check if provider already exists for this user
    existing_provider = (
        db.query(LLMSetting)
        .filter(
            LLMSetting.user_id == current_user.id,
            LLMSetting.provider == provider_data.provider,
        )
        .first()
    )

    if existing_provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider {provider_data.provider} already configured",
        )

    # Encrypt the API key
    encrypted_api_key = encryption_manager.encrypt(provider_data.api_key)

    # Create new provider setting
    new_provider = LLMSetting(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        provider=provider_data.provider,
        encrypted_api_key=encrypted_api_key,
        base_url=provider_data.base_url,
        is_active=True,
        metadata=provider_data.metadata,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(new_provider)
    db.commit()
    db.refresh(new_provider)

    return LLMProviderInfo(
        id=new_provider.id,
        provider=new_provider.provider,
        base_url=new_provider.base_url,
        is_active=new_provider.is_active,
        has_api_key=bool(new_provider.encrypted_api_key),
        created_at=new_provider.created_at.isoformat()
        if new_provider.created_at
        else "",
        updated_at=new_provider.updated_at.isoformat()
        if new_provider.updated_at
        else None,
        metadata=new_provider.metadata,
    )


@router.get("/llm-providers/{provider_id}", response_model=LLMProviderInfo)
async def get_llm_provider(
    provider_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific LLM provider setting."""

    provider = (
        db.query(LLMSetting)
        .filter(LLMSetting.id == provider_id, LLMSetting.user_id == current_user.id)
        .first()
    )

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )

    return LLMProviderInfo(
        id=provider.id,
        provider=provider.provider,
        base_url=provider.base_url,
        is_active=provider.is_active,
        has_api_key=bool(provider.encrypted_api_key),
        created_at=provider.created_at.isoformat() if provider.created_at else "",
        updated_at=provider.updated_at.isoformat() if provider.updated_at else None,
        metadata=provider.metadata,
    )


@router.patch("/llm-providers/{provider_id}", response_model=LLMProviderInfo)
async def update_llm_provider(
    provider_id: str,
    provider_data: LLMProviderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an LLM provider setting."""

    provider = (
        db.query(LLMSetting)
        .filter(LLMSetting.id == provider_id, LLMSetting.user_id == current_user.id)
        .first()
    )

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )

    # Update fields
    if provider_data.api_key is not None:
        provider.encrypted_api_key = encryption_manager.encrypt(provider_data.api_key)
    if provider_data.base_url is not None:
        provider.base_url = provider_data.base_url
    if provider_data.is_active is not None:
        provider.is_active = provider_data.is_active
    if provider_data.metadata is not None:
        provider.metadata = provider_data.metadata

    provider.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(provider)

    return LLMProviderInfo(
        id=provider.id,
        provider=provider.provider,
        base_url=provider.base_url,
        is_active=provider.is_active,
        has_api_key=bool(provider.encrypted_api_key),
        created_at=provider.created_at.isoformat() if provider.created_at else "",
        updated_at=provider.updated_at.isoformat() if provider.updated_at else None,
        metadata=provider.metadata,
    )


@router.delete("/llm-providers/{provider_id}")
async def delete_llm_provider(
    provider_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an LLM provider setting."""

    provider = (
        db.query(LLMSetting)
        .filter(LLMSetting.id == provider_id, LLMSetting.user_id == current_user.id)
        .first()
    )

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found"
        )

    db.delete(provider)
    db.commit()

    return {"message": "Provider deleted successfully"}


@router.post("/llm-providers/test", response_model=ProviderValidation)
async def test_api_key(
    test_data: APIKeyTest, current_user: User = Depends(get_current_user)
):
    """Test an API key for a specific provider."""

    # Mock validation - in real implementation, this would test the actual API
    try:
        # Simulate API key validation
        if len(test_data.api_key) < 10:
            return ProviderValidation(
                provider=test_data.provider,
                valid=False,
                error_message="API key appears to be too short",
            )

        # Mock successful validation
        supported_models = {
            "openai": ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"],
            "anthropic": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
            "gemini": ["gemini-pro", "gemini-pro-vision"],
            "azure": ["gpt-4", "gpt-35-turbo"],
            "bedrock": ["claude-3-sonnet", "claude-3-haiku"],
        }

        return ProviderValidation(
            provider=test_data.provider,
            valid=True,
            supported_models=supported_models.get(test_data.provider, []),
        )

    except Exception as e:
        return ProviderValidation(
            provider=test_data.provider, valid=False, error_message=str(e)
        )


@router.get("/mcp-configs", response_model=MCPConfigList)
async def list_mcp_configs(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """List user's MCP configurations."""

    configs = (
        db.query(MCPSetting)
        .filter(MCPSetting.user_id == current_user.id)
        .order_by(MCPSetting.created_at)
        .all()
    )

    config_list = [
        MCPConfigInfo(
            id=config.id,
            mcp_config=config.mcp_config,
            is_active=config.is_active,
            created_at=config.created_at.isoformat() if config.created_at else "",
            updated_at=config.updated_at.isoformat() if config.updated_at else None,
        )
        for config in configs
    ]

    return MCPConfigList(configurations=config_list)


@router.post(
    "/mcp-configs", response_model=MCPConfigInfo, status_code=status.HTTP_201_CREATED
)
async def create_mcp_config(
    config_data: MCPConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new MCP configuration."""

    # Create new MCP configuration
    new_config = MCPSetting(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        mcp_config=config_data.mcp_config,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    return MCPConfigInfo(
        id=new_config.id,
        mcp_config=new_config.mcp_config,
        is_active=new_config.is_active,
        created_at=new_config.created_at.isoformat() if new_config.created_at else "",
        updated_at=new_config.updated_at.isoformat() if new_config.updated_at else None,
    )


@router.get("/mcp-configs/{config_id}", response_model=MCPConfigInfo)
async def get_mcp_config(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific MCP configuration."""

    config = (
        db.query(MCPSetting)
        .filter(MCPSetting.id == config_id, MCPSetting.user_id == current_user.id)
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP configuration not found"
        )

    return MCPConfigInfo(
        id=config.id,
        mcp_config=config.mcp_config,
        is_active=config.is_active,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.patch("/mcp-configs/{config_id}", response_model=MCPConfigInfo)
async def update_mcp_config(
    config_id: str,
    config_data: MCPConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an MCP configuration."""

    config = (
        db.query(MCPSetting)
        .filter(MCPSetting.id == config_id, MCPSetting.user_id == current_user.id)
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP configuration not found"
        )

    # Update fields
    if config_data.mcp_config is not None:
        config.mcp_config = config_data.mcp_config
    if config_data.is_active is not None:
        config.is_active = config_data.is_active

    config.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(config)

    return MCPConfigInfo(
        id=config.id,
        mcp_config=config.mcp_config,
        is_active=config.is_active,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.delete("/mcp-configs/{config_id}")
async def delete_mcp_config(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an MCP configuration."""

    config = (
        db.query(MCPSetting)
        .filter(MCPSetting.id == config_id, MCPSetting.user_id == current_user.id)
        .first()
    )

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP configuration not found"
        )

    db.delete(config)
    db.commit()

    return {"message": "MCP configuration deleted successfully"}


@router.get("/export", response_model=SettingsExport)
async def export_settings(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Export user's settings."""

    # Get LLM providers (without decrypted API keys)
    llm_providers = (
        db.query(LLMSetting).filter(LLMSetting.user_id == current_user.id).all()
    )

    provider_list = [
        LLMProviderInfo(
            id=provider.id,
            provider=provider.provider,
            base_url=provider.base_url,
            is_active=provider.is_active,
            has_api_key=bool(provider.encrypted_api_key),
            created_at=provider.created_at.isoformat() if provider.created_at else "",
            updated_at=provider.updated_at.isoformat() if provider.updated_at else None,
            metadata=provider.metadata,
        )
        for provider in llm_providers
    ]

    # Get MCP configurations
    mcp_configs = (
        db.query(MCPSetting).filter(MCPSetting.user_id == current_user.id).all()
    )

    config_list = [
        MCPConfigInfo(
            id=config.id,
            mcp_config=config.mcp_config,
            is_active=config.is_active,
            created_at=config.created_at.isoformat() if config.created_at else "",
            updated_at=config.updated_at.isoformat() if config.updated_at else None,
        )
        for config in mcp_configs
    ]

    return SettingsExport(
        llm_providers=provider_list,
        mcp_configurations=config_list,
        export_timestamp=datetime.now(timezone.utc).isoformat(),
    )
