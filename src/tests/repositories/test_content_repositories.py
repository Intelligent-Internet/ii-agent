from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.content.media.models import MediaTemplate
from ii_agent.content.media.repository import MediaTemplateRepository
from ii_agent.settings.skills.models import Skill, SkillSource
from ii_agent.settings.skills.repository import SkillRepository
from ii_agent.content.slides.repository import SlideContentRepository
from ii_agent.content.slides.templates.repository import SlideTemplateRepository
from ii_agent.content.storybook.models import Storybook, StorybookPage
from ii_agent.content.storybook.repository import StorybookRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_media_template_repository_pagination_and_filters(
    db_session: AsyncSession,
) -> None:
    media_id_1 = uuid.uuid4()
    media_id_2 = uuid.uuid4()
    media_id_3 = uuid.uuid4()
    repo = MediaTemplateRepository()
    db_session.add_all(
        [
            MediaTemplate(
                id=media_id_1,
                name="Landscape Shot",
                prompt="A landscape",
                type="image",
            ),
            MediaTemplate(
                id=media_id_2,
                name="Portrait Shot",
                prompt="A portrait",
                type="image",
            ),
            MediaTemplate(
                id=media_id_3,
                name="Voice Intro",
                prompt="Narration",
                type="audio",
            ),
        ]
    )
    await db_session.flush()

    by_id = await repo.get_by_id(db_session, media_id_1)
    by_name = await repo.get_by_name(db_session, "Portrait Shot")
    assert by_id is not None
    assert by_name is not None

    paged = await repo.list_templates(
        db_session, page=0, page_size=2, search="Shot", media_type="image"
    )
    unfiltered = await repo.list_templates(db_session, page=0, page_size=10)
    assert paged["total"] == 2
    assert paged["page_size"] == 2
    assert len(paged["templates"]) == 2
    assert unfiltered["total"] == 3
    assert len(unfiltered["templates"]) == 3


async def test_skill_repository_builtin_user_scopes_and_delete(
    db_session: AsyncSession,
    user_factory,
) -> None:
    repo = SkillRepository()
    user = await user_factory()
    other_user = await user_factory()

    builtin_skill = Skill(
        id=uuid.uuid4(),
        user_id=None,
        name="lint-skill",
        description="Builtin lint skill",
        source=SkillSource.BUILTIN.value,
        skill_md_content="# lint",
        sandbox_path="/skills/lint",
        storage_uri="gcs://skills/lint",
    )
    user_skill = Skill(
        id=uuid.uuid4(),
        user_id=user.id,
        name="deploy-skill",
        description="User deploy skill",
        source=SkillSource.GITHUB.value,
        source_url="https://github.com/acme/deploy",
        skill_md_content="# deploy",
        sandbox_path="/skills/deploy",
        storage_uri="gcs://skills/deploy",
    )
    builtin_override = Skill(
        id=uuid.uuid4(),
        user_id=user.id,
        name="lint-skill-override",
        description="User override for builtin",
        source=SkillSource.BUILTIN.value,
        skill_md_content="# override",
        sandbox_path="/skills/lint-override",
        storage_uri="gcs://skills/lint-override",
    )
    db_session.add_all([builtin_skill, user_skill, builtin_override])
    await db_session.flush()

    assert await repo.get_builtin_by_id(db_session, builtin_skill.id) is not None
    assert await repo.get_by_id_for_user(db_session, builtin_skill.id, user.id) is not None
    assert await repo.get_user_skill(db_session, user_skill.id, user.id) is not None
    assert await repo.get_user_skill(db_session, user_skill.id, other_user.id) is None
    assert await repo.get_by_name_and_user(db_session, "deploy-skill", user.id) is not None
    assert (
        await repo.get_user_builtin_override(db_session, user.id, "lint-skill-override")
    ) is not None

    user_skills = await repo.list_by_user(db_session, user.id)
    builtin_skills = await repo.list_builtin(db_session)
    assert len(user_skills) == 2
    assert len(builtin_skills) == 1

    await repo.delete(db_session, user_skill)
    assert await repo.get_user_skill(db_session, user_skill.id, user.id) is None


async def test_slide_content_repository_upsert_and_summary(
    db_session: AsyncSession,
    session_factory,
) -> None:
    repo = SlideContentRepository()
    session = await session_factory()

    first_id = await repo.upsert_slide(
        db_session,
        session_id=session.id,
        presentation_name="Kickoff",
        slide_number=1,
        slide_title="Intro",
        slide_content="<h1>Welcome</h1>",
        tool_name="slide-tool",
    )
    same_id = await repo.upsert_slide(
        db_session,
        session_id=session.id,
        presentation_name="Kickoff",
        slide_number=1,
        slide_title="Intro Updated",
        slide_content="<h1>Hello</h1>",
        tool_name="slide-tool",
    )
    await repo.upsert_slide(
        db_session,
        session_id=session.id,
        presentation_name="Roadmap",
        slide_number=1,
        slide_title="Q1",
        slide_content="<p>Roadmap</p>",
        tool_name="slide-tool",
    )

    assert same_id == first_id

    updated = await repo.get_by_session_and_presentation_and_number(
        db_session, session.id, "Kickoff", 1
    )
    assert updated is not None
    assert updated.slide_title == "Intro Updated"

    kickoff_slides = await repo.get_slides_by_session_and_presentation(
        db_session, session.id, "Kickoff"
    )
    assert len(kickoff_slides) == 1

    all_slides = await repo.get_slides_by_session(db_session, session.id)
    assert len(all_slides) == 2
    kickoff_from_optional_filter = await repo.get_slides_by_session(
        db_session, session.id, presentation_name="Kickoff"
    )
    assert len(kickoff_from_optional_filter) == 1

    summary = await repo.get_presentations_summary(db_session, session.id)
    assert len(summary) == 2
    assert {row.presentation_name for row in summary} == {"Kickoff", "Roadmap"}


async def test_slide_template_repository_create_get_and_paginated_search(
    db_session: AsyncSession,
) -> None:
    repo = SlideTemplateRepository()

    created_a = await repo.create(
        db_session,
        template_name="Investor Deck",
        content="<section>Investor</section>",
    )
    await repo.create(
        db_session,
        template_name="Sales Deck",
        content="<section>Sales</section>",
    )
    await repo.create(
        db_session,
        template_name="Engineering Review",
        content="<section>Engineering</section>",
    )

    by_id = await repo.get_by_id(db_session, created_a.id)
    full = await repo.get_full_by_id(db_session, created_a.id)
    paged = await repo.list_paginated(db_session, page=1, page_size=2, search="Deck")
    paged_no_search = await repo.list_paginated(db_session, page=1, page_size=10)
    missing_by_id = await repo.get_by_id(db_session, uuid.uuid4())
    missing_full = await repo.get_full_by_id(db_session, uuid.uuid4())

    assert by_id is not None
    assert by_id["slide_template_name"] == "Investor Deck"
    assert full is not None
    assert full.slide_template_name == "Investor Deck"
    assert paged["total"] == 2
    assert paged["total_pages"] == 1
    assert paged_no_search["total"] == 3
    assert paged_no_search["total_pages"] == 1
    assert missing_by_id is None
    assert missing_full is None


async def test_storybook_repository_create_pages_and_generation_updates(
    db_session: AsyncSession,
    session_factory,
) -> None:
    repo = StorybookRepository()
    session = await session_factory()

    storybook = Storybook(
        id=uuid.uuid4(),
        session_id=session.id,
        name="Storybook Alpha",
        version=1,
        style_json={},
        aspect_ratio="16:9",
        resolution="2K",
    )
    created = await repo.save(db_session, storybook)

    pages = [
        StorybookPage(id=uuid.uuid4(), page_number=1, text_content="Page 1"),
        StorybookPage(id=uuid.uuid4(), page_number=2, text_content="Page 2"),
    ]
    await repo.create_pages_batch(db_session, pages, created.id)

    loaded = await repo.get_by_id(db_session, created.id)
    assert loaded is not None
    assert len(loaded.pages) == 2

    page_1 = await repo.get_page_by_number(db_session, created.id, 1)
    assert page_1 is not None

    updated_page = await repo.update_page(
        db_session, page_1.id, html_content="<p>Updated</p>", image_url="img://1"
    )
    assert updated_page is not None
    assert updated_page.html_content == "<p>Updated</p>"

    updated_storybook = await repo.update_generation_status(
        db_session,
        created.id,
        status="running",
        total_pages=10,
        completed_pages=4,
        generating_pages=[5],
        generation_meta={"worker": "w1"},
    )
    assert updated_storybook is not None
    generation = updated_storybook.style_json["generation"]
    assert generation["status"] == "running"
    assert generation["completed_pages"] == 4


async def test_storybook_repository_single_page_not_found_and_version_paths(
    db_session: AsyncSession,
    session_factory,
) -> None:
    repo = StorybookRepository()
    session = await session_factory()

    root = Storybook(
        id=uuid.uuid4(),
        session_id=session.id,
        name="Root",
        version=1,
        style_json=None,
        aspect_ratio="1:1",
        resolution="1K",
    )
    child = Storybook(
        id=uuid.uuid4(),
        session_id=session.id,
        name="Child",
        version=2,
        root_storybook_id=root.id,
        parent_storybook_id=root.id,
        style_json={},
        aspect_ratio="1:1",
        resolution="1K",
    )
    await repo.save(db_session, root)
    await repo.save(db_session, child)

    page = StorybookPage(
        id=uuid.uuid4(),
        page_number=1,
        text_content="First Page",
    )
    created_page = await repo.create_page(db_session, page, root.id)
    assert created_page.id == page.id
    assert await repo.get_page_by_number(db_session, root.id, 1) is not None

    storybooks = await repo.get_by_session_id(db_session, session.id)
    assert {storybook.id for storybook in storybooks} == {root.id, child.id}

    updated_page = await repo.update_page(
        db_session,
        page.id,
        text_content="Updated text",
        audio_link="audio://clip",
    )
    assert updated_page is not None
    assert updated_page.text_content == "Updated text"
    assert updated_page.audio_link == "audio://clip"

    assert await repo.update_page(db_session, uuid.uuid4(), html_content="<p>x</p>") is None
    assert (
        await repo.update_generation_status(
            db_session,
            uuid.uuid4(),
            status="failed",
            error_message="missing",
        )
        is None
    )

    failed_generation = await repo.update_generation_status(
        db_session,
        root.id,
        status="failed",
        error_message="boom",
    )
    assert failed_generation is not None
    generation = failed_generation.style_json["generation"]
    assert generation["status"] == "failed"
    assert generation["error_message"] == "boom"

    without_status = await repo.update_generation_status(
        db_session,
        root.id,
        total_pages=9,
    )
    assert without_status is not None
    assert without_status.style_json["generation"]["total_pages"] == 9

    version_family = await repo.get_version_family(db_session, root.id)
    assert [storybook.id for storybook in version_family] == [child.id, root.id]
