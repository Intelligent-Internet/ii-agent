"""API routes for users domain."""

import copy
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.users.dependencies import UserServiceDep

router = APIRouter(prefix="/auth", tags=["Users"])


@router.patch("/me/language")
async def update_user_language(
    current_user: CurrentUser,
    db: DBSession,
    user_service: UserServiceDep,
    language: str,
) -> dict[str, str]:
    """Update user's preferred language."""
    await user_service.update_language(db, current_user, language)
    return {"message": "Language updated successfully", "language": language}


class UpdatePreferencesRequest(BaseModel):
    has_memory: Optional[bool] = None


@router.patch("/me/preferences")
async def update_user_preferences(
    current_user: CurrentUser,
    db: DBSession,
    body: UpdatePreferencesRequest,
) -> dict[str, Any]:
    """Update user preference settings (memory, personalization)."""
    metadata = copy.deepcopy(current_user.user_metadata) if isinstance(current_user.user_metadata, dict) else {}
    old_prefs = metadata.get("preferences", {})
    updates = body.model_dump(exclude_none=True)
    metadata["preferences"] = {**old_prefs, **updates}

    current_user.user_metadata = metadata
    await db.commit()

    # Evict cached memory preferences so the next agent run sees the new value
    try:
        from ii_agent.core.container import get_app_container

        container = get_app_container()
        await container.memory_service._cache.evict_user_prefs(str(current_user.id))
    except Exception:
        pass  # cache eviction is best-effort

    return {"message": "Preferences updated successfully", "preferences": current_user.preferences}


@router.delete("/me")
async def delete_user_account(
    current_user: CurrentUser,
    db: DBSession,
    user_service: UserServiceDep,
) -> dict[str, str]:
    """Soft delete user account by setting is_active to False."""
    await user_service.delete_user(db, current_user)
    return {"message": "Account deleted successfully"}
