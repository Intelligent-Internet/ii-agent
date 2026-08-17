"""Tests for ii_agent.core.storage.path_resolver — PathResolver methods."""

from __future__ import annotations

import uuid


class TestPathResolver:
    def _make_resolver(self):
        from ii_agent.core.storage.path_resolver import PathResolver

        return PathResolver()

    def test_user_skill(self):
        r = self._make_resolver()
        uid = uuid.uuid4()
        result = r.user_skill(uid, "my-skill")
        assert f"users/{uid}/skills/my-skill.zip" == result

    def test_content_template(self):
        r = self._make_resolver()
        result = r.content_template("slides", "header", "png")
        assert "content/templates/slides/header.png" == result

    def test_slide_asset(self):
        r = self._make_resolver()
        result = r.slide_asset("abc123", "html")
        assert "content/slides/abc123.html" == result

    def test_system_asset(self):
        r = self._make_resolver()
        result = r.system_asset("fonts", "roboto", "ttf")
        assert "system/fonts/roboto.ttf" == result

    def test_temp_file(self):
        r = self._make_resolver()
        result = r.temp_file("tok123", "upload", "pdf")
        assert "tmp/tok123/upload.pdf" == result

    def test_is_user_content_true(self):
        r = self._make_resolver()
        assert r.is_user_content("users/abc-123/files/doc.pdf") is True

    def test_is_user_content_false(self):
        r = self._make_resolver()
        assert r.is_user_content("system/data/file.txt") is False

    def test_user_prefix(self):
        r = self._make_resolver()
        uid = uuid.uuid4()
        assert r.user_prefix(uid) == f"users/{uid}/"

    def test_user_media_prefix(self):
        r = self._make_resolver()
        uid = uuid.uuid4()
        assert r.user_media_prefix(uid) == f"users/{uid}/media/"

    def test_user_type_prefix_known_type(self):
        r = self._make_resolver()
        uid = uuid.uuid4()
        result = r.user_type_prefix(uid, "image")
        # Should use the folder from _TYPE_FOLDERS for 'image'
        assert str(uid) in result

    def test_user_type_prefix_unknown_type(self):
        r = self._make_resolver()
        uid = uuid.uuid4()
        result = r.user_type_prefix(uid, "unknown_type_xyz")
        assert str(uid) in result
