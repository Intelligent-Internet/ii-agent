"""Tests for ii_agent.settings.skills.loader — pure functions and async DB logic."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.settings.skills.loader import (
    SANDBOX_SKILLS_PATH,
    _user_ids_match,
    get_skill_by_name,
    get_user_skills,
    load_builtin_skills,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestSandboxSkillsPath:
    def test_path_value(self):
        assert SANDBOX_SKILLS_PATH == "/workspace/.skills"


# ---------------------------------------------------------------------------
# _user_ids_match
# ---------------------------------------------------------------------------


class TestUserIdsMatch:
    def test_none_skill_user_id_returns_false(self):
        assert _user_ids_match(None, uuid.uuid4()) is False

    def test_matching_uuid_returns_true(self):
        uid = uuid.uuid4()
        assert _user_ids_match(uid, uid) is True

    def test_different_uuid_returns_false(self):
        uid1 = uuid.uuid4()
        uid2 = uuid.uuid4()
        assert _user_ids_match(uid1, uid2) is False

    def test_uuid_string_vs_uuid_object_mismatch(self):
        uid = uuid.uuid4()
        # ORM may return UUID objects; comparing UUID to str should return False
        assert _user_ids_match(str(uid), uid) is False


# ---------------------------------------------------------------------------
# load_builtin_skills
# ---------------------------------------------------------------------------


def _make_fake_skill_dir(tmp_path: Path, name: str, skill_md: str) -> Path:
    """Create a fake skill directory with a SKILL.md file."""
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(skill_md)
    return skill_dir


MINIMAL_SKILL_MD = """---
name: test-skill
description: A test skill
license: MIT
---

Body content here.
"""

SKILL_WITH_TOOLS_MD = """---
name: tool-skill
description: A skill with allowed tools
allowed_tools: python node
license: MIT
---

Body content here.
"""


class TestLoadBuiltinSkills:
    def test_returns_list(self, tmp_path: Path):
        props = MagicMock()
        props.name = "test-skill"
        props.description = "A test skill"
        props.license = "MIT"
        props.compatibility = None
        props.allowed_tools = None

        skill_dir = _make_fake_skill_dir(tmp_path, "test-skill", MINIMAL_SKILL_MD)

        with (
            patch(
                "ii_agent.settings.skills.loader.get_builtin_skill_dirs",
                return_value=[skill_dir],
            ),
            patch(
                "ii_agent.settings.skills.loader.read_properties",
                return_value=props,
            ),
        ):
            skills = load_builtin_skills()

        assert isinstance(skills, list)
        assert len(skills) == 1

    def test_skill_has_required_keys(self, tmp_path: Path):
        props = MagicMock()
        props.name = "my-skill"
        props.description = "Desc"
        props.license = "MIT"
        props.compatibility = None
        props.allowed_tools = None

        skill_dir = _make_fake_skill_dir(tmp_path, "my-skill", MINIMAL_SKILL_MD)

        with (
            patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[skill_dir]),
            patch("ii_agent.settings.skills.loader.read_properties", return_value=props),
        ):
            skills = load_builtin_skills()

        skill = skills[0]
        assert "name" in skill
        assert "description" in skill
        assert "skill_md_content" in skill
        assert "source" in skill
        assert "sandbox_path" in skill
        assert "storage_uri" in skill

    def test_sandbox_path_uses_skill_name(self, tmp_path: Path):
        props = MagicMock()
        props.name = "my-tool"
        props.description = "Desc"
        props.license = None
        props.compatibility = None
        props.allowed_tools = None

        skill_dir = _make_fake_skill_dir(tmp_path, "my-tool", MINIMAL_SKILL_MD)

        with (
            patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[skill_dir]),
            patch("ii_agent.settings.skills.loader.read_properties", return_value=props),
        ):
            skills = load_builtin_skills()

        assert skills[0]["sandbox_path"] == f"{SANDBOX_SKILLS_PATH}/my-tool"

    def test_storage_uri_uses_builtin_prefix(self, tmp_path: Path):
        props = MagicMock()
        props.name = "my-tool"
        props.description = "Desc"
        props.license = None
        props.compatibility = None
        props.allowed_tools = None

        skill_dir = _make_fake_skill_dir(tmp_path, "my-tool", MINIMAL_SKILL_MD)

        with (
            patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[skill_dir]),
            patch("ii_agent.settings.skills.loader.read_properties", return_value=props),
        ):
            skills = load_builtin_skills()

        storage_uri = skills[0]["storage_uri"]
        assert storage_uri.startswith("builtin:")

    def test_allowed_tools_split_from_string(self, tmp_path: Path):
        props = MagicMock()
        props.name = "multi-tool"
        props.description = "D"
        props.license = None
        props.compatibility = None
        props.allowed_tools = "python node shell"

        skill_dir = _make_fake_skill_dir(tmp_path, "multi-tool", MINIMAL_SKILL_MD)

        with (
            patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[skill_dir]),
            patch("ii_agent.settings.skills.loader.read_properties", return_value=props),
        ):
            skills = load_builtin_skills()

        assert skills[0]["allowed_tools"] == ["python", "node", "shell"]

    def test_none_allowed_tools_becomes_empty_list(self, tmp_path: Path):
        props = MagicMock()
        props.name = "no-tool"
        props.description = "D"
        props.license = None
        props.compatibility = None
        props.allowed_tools = None

        skill_dir = _make_fake_skill_dir(tmp_path, "no-tool", MINIMAL_SKILL_MD)

        with (
            patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[skill_dir]),
            patch("ii_agent.settings.skills.loader.read_properties", return_value=props),
        ):
            skills = load_builtin_skills()

        assert skills[0]["allowed_tools"] == []

    def test_error_in_skill_dir_is_skipped(self, tmp_path: Path):
        """If one skill directory errors, it should be skipped."""
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("bad content")

        with (
            patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[skill_dir]),
            patch("ii_agent.settings.skills.loader.read_properties", side_effect=Exception("parse error")),
        ):
            skills = load_builtin_skills()

        assert skills == []

    def test_skill_md_content_stored_in_result(self, tmp_path: Path):
        content = MINIMAL_SKILL_MD
        props = MagicMock()
        props.name = "content-skill"
        props.description = "D"
        props.license = None
        props.compatibility = None
        props.allowed_tools = None

        skill_dir = _make_fake_skill_dir(tmp_path, "content-skill", content)

        with (
            patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[skill_dir]),
            patch("ii_agent.settings.skills.loader.read_properties", return_value=props),
        ):
            skills = load_builtin_skills()

        assert skills[0]["skill_md_content"] == content

    def test_empty_skill_dirs_returns_empty_list(self):
        with patch("ii_agent.settings.skills.loader.get_builtin_skill_dirs", return_value=[]):
            skills = load_builtin_skills()
        assert skills == []


# ---------------------------------------------------------------------------
# get_user_skills
# ---------------------------------------------------------------------------


def _make_skill(name: str, user_id: Optional[uuid.UUID], is_enabled: bool = True) -> MagicMock:
    skill = MagicMock()
    skill.name = name
    skill.user_id = user_id
    skill.is_enabled = is_enabled
    return skill


class TestGetUserSkills:
    @pytest.mark.asyncio
    async def test_returns_builtin_skills_when_no_user_skills(self):
        user_id = uuid.uuid4()
        builtin = _make_skill("pdf", user_id=None, is_enabled=True)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [builtin]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(db, user_id)

        assert len(skills) == 1
        assert skills[0].name == "pdf"

    @pytest.mark.asyncio
    async def test_user_skill_overrides_builtin(self):
        user_id = uuid.uuid4()
        builtin = _make_skill("pdf", user_id=None, is_enabled=True)
        user_override = _make_skill("pdf", user_id=user_id, is_enabled=True)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [builtin, user_override]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(db, user_id)

        assert len(skills) == 1
        assert skills[0] is user_override

    @pytest.mark.asyncio
    async def test_disabled_skills_excluded_when_enabled_only(self):
        user_id = uuid.uuid4()
        disabled = _make_skill("pdf", user_id=None, is_enabled=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [disabled]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(db, user_id, enabled_only=True)

        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_disabled_skills_included_when_enabled_only_false(self):
        user_id = uuid.uuid4()
        disabled_builtin = _make_skill("pdf", user_id=None, is_enabled=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [disabled_builtin]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(db, user_id, enabled_only=False)

        assert len(skills) == 1

    @pytest.mark.asyncio
    async def test_user_disabled_override_excludes_builtin(self):
        """User disabling a builtin skill via override should exclude both."""
        user_id = uuid.uuid4()
        builtin = _make_skill("pdf", user_id=None, is_enabled=True)
        user_disabled = _make_skill("pdf", user_id=user_id, is_enabled=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [builtin, user_disabled]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        # enabled_only=True; user disabled override should win
        skills = await get_user_skills(db, user_id, enabled_only=True)

        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        user_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(db, user_id)

        assert skills == []


# ---------------------------------------------------------------------------
# get_skill_by_name
# ---------------------------------------------------------------------------


class TestGetSkillByName:
    @pytest.mark.asyncio
    async def test_returns_user_skill_when_enabled(self):
        user_id = uuid.uuid4()
        user_skill = _make_skill("pdf", user_id=user_id, is_enabled=True)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user_skill

        db = AsyncMock()
        db.execute = AsyncMock(return_value=user_result)

        result = await get_skill_by_name(db, user_id, "pdf")

        assert result is user_skill

    @pytest.mark.asyncio
    async def test_returns_none_when_user_skill_disabled(self):
        user_id = uuid.uuid4()
        user_skill = _make_skill("pdf", user_id=user_id, is_enabled=False)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user_skill

        db = AsyncMock()
        db.execute = AsyncMock(return_value=user_result)

        result = await get_skill_by_name(db, user_id, "pdf")

        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_builtin_when_no_user_skill(self):
        user_id = uuid.uuid4()
        builtin = _make_skill("pdf", user_id=None, is_enabled=True)

        no_user_skill_result = MagicMock()
        no_user_skill_result.scalar_one_or_none.return_value = None

        builtin_result = MagicMock()
        builtin_result.scalar_one_or_none.return_value = builtin

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[no_user_skill_result, builtin_result])

        result = await get_skill_by_name(db, user_id, "pdf")

        assert result is builtin

    @pytest.mark.asyncio
    async def test_returns_none_when_neither_user_nor_builtin(self):
        user_id = uuid.uuid4()

        no_result = MagicMock()
        no_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[no_result, no_result])

        result = await get_skill_by_name(db, user_id, "nonexistent")

        assert result is None
