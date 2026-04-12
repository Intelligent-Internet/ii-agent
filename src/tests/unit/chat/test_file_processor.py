"""Unit tests for ii_agent.chat.file_processor pure utility functions and extractors."""

from __future__ import annotations

import io
import json


from ii_agent.chat.application.file_processor import (
    ContentExtractorFactory,
    CodeExtractor,
    CSVExtractor,
    JSONExtractor,
    MarkdownExtractor,
    ProcessedFiles,
    TextExtractor,
    XMLExtractor,
    is_binary_file,
    is_remote_url,
    is_text_extractable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(content: bytes) -> io.BytesIO:
    """Return an in-memory binary file-like object."""
    return io.BytesIO(content)


# ===========================================================================
# is_binary_file()
# ===========================================================================


class TestIsBinaryFile:
    """Tests for is_binary_file()."""

    # --- content_type-based detection ---

    def test_pdf_content_type_returns_true(self):
        assert is_binary_file("application/pdf", "document.pdf") is True

    def test_image_png_content_type_returns_true(self):
        assert is_binary_file("image/png", "photo.png") is True

    def test_image_jpeg_content_type_returns_true(self):
        assert is_binary_file("image/jpeg", "photo.jpg") is True

    def test_image_gif_content_type_returns_true(self):
        assert is_binary_file("image/gif", "anim.gif") is True

    def test_image_webp_content_type_returns_true(self):
        assert is_binary_file("image/webp", "image.webp") is True

    def test_generic_image_subtype_content_type_returns_true(self):
        # Any image/* subtype should be treated as binary.
        assert is_binary_file("image/svg+xml", "diagram.svg") is True

    def test_text_plain_content_type_returns_false(self):
        assert is_binary_file("text/plain", "readme.txt") is False

    def test_application_json_content_type_returns_false(self):
        assert is_binary_file("application/json", "data.json") is False

    def test_text_csv_content_type_returns_false(self):
        assert is_binary_file("text/csv", "data.csv") is False

    # --- None content_type: extension-based detection ---

    def test_none_content_type_pdf_extension_returns_true(self):
        assert is_binary_file(None, "report.pdf") is True

    def test_none_content_type_png_extension_returns_true(self):
        assert is_binary_file(None, "image.png") is True

    def test_none_content_type_jpg_extension_returns_true(self):
        assert is_binary_file(None, "photo.jpg") is True

    def test_none_content_type_jpeg_extension_returns_true(self):
        assert is_binary_file(None, "photo.jpeg") is True

    def test_none_content_type_gif_extension_returns_true(self):
        assert is_binary_file(None, "anim.gif") is True

    def test_none_content_type_webp_extension_returns_true(self):
        assert is_binary_file(None, "img.webp") is True

    def test_none_content_type_uppercase_extension_returns_true(self):
        # File name comparison should be case-insensitive.
        assert is_binary_file(None, "IMAGE.PNG") is True

    def test_none_content_type_txt_extension_returns_false(self):
        assert is_binary_file(None, "notes.txt") is False

    def test_none_content_type_md_extension_returns_false(self):
        assert is_binary_file(None, "README.md") is False

    def test_none_content_type_unknown_extension_returns_false(self):
        assert is_binary_file(None, "archive.tar.gz") is False


# ===========================================================================
# is_remote_url()
# ===========================================================================


class TestIsRemoteUrl:
    """Tests for is_remote_url()."""

    def test_http_url_returns_true(self):
        assert is_remote_url("http://example.com/file.pdf") is True

    def test_https_url_returns_true(self):
        assert is_remote_url("https://example.com/image.png") is True

    def test_http_localhost_url_returns_true(self):
        assert is_remote_url("http://localhost:8080/file") is True

    def test_absolute_file_path_returns_false(self):
        assert is_remote_url("/home/user/file.txt") is False

    def test_relative_file_path_returns_false(self):
        assert is_remote_url("relative/path/file.txt") is False

    def test_bare_filename_returns_false(self):
        assert is_remote_url("document.pdf") is False

    def test_ftp_url_returns_false(self):
        # Only http/https are remote; ftp is not.
        assert is_remote_url("ftp://files.example.com/data.zip") is False

    def test_file_scheme_returns_false(self):
        assert is_remote_url("file:///home/user/doc.pdf") is False

    def test_empty_string_returns_false(self):
        assert is_remote_url("") is False


# ===========================================================================
# is_text_extractable()
# ===========================================================================


class TestIsTextExtractable:
    """Tests for is_text_extractable()."""

    # --- content_type-based ---

    def test_text_plain_content_type_returns_true(self):
        assert is_text_extractable("text/plain", "readme.txt") is True

    def test_text_markdown_content_type_returns_true(self):
        assert is_text_extractable("text/markdown", "notes.md") is True

    def test_application_json_content_type_returns_true(self):
        assert is_text_extractable("application/json", "data.json") is True

    def test_text_csv_content_type_returns_true(self):
        assert is_text_extractable("text/csv", "report.csv") is True

    def test_text_xml_content_type_returns_true(self):
        assert is_text_extractable("text/xml", "feed.xml") is True

    def test_application_xml_content_type_returns_true(self):
        assert is_text_extractable("application/xml", "config.xml") is True

    def test_text_javascript_content_type_returns_true(self):
        assert is_text_extractable("text/javascript", "script.js") is True

    def test_text_html_content_type_returns_true(self):
        assert is_text_extractable("text/html", "page.html") is True

    def test_pdf_content_type_returns_false(self):
        # PDF is binary, not text-extractable via these extractors.
        assert is_text_extractable("application/pdf", "doc.pdf") is False

    def test_image_png_content_type_returns_false(self):
        assert is_text_extractable("image/png", "photo.png") is False

    def test_unknown_content_type_with_txt_extension_returns_true(self):
        assert is_text_extractable("application/octet-stream", "notes.txt") is True

    # --- extension-based fallback ---

    def test_txt_extension_returns_true(self):
        assert is_text_extractable(None, "readme.txt") is True

    def test_md_extension_returns_true(self):
        assert is_text_extractable(None, "notes.md") is True

    def test_py_extension_returns_true(self):
        assert is_text_extractable(None, "script.py") is True

    def test_js_extension_returns_true(self):
        assert is_text_extractable(None, "app.js") is True

    def test_json_extension_returns_true(self):
        assert is_text_extractable(None, "data.json") is True

    def test_csv_extension_returns_true(self):
        assert is_text_extractable(None, "report.csv") is True

    def test_xml_extension_returns_true(self):
        assert is_text_extractable(None, "config.xml") is True

    def test_html_extension_returns_true(self):
        assert is_text_extractable(None, "index.html") is True

    def test_sql_extension_returns_true(self):
        assert is_text_extractable(None, "query.sql") is True

    def test_png_extension_returns_false(self):
        assert is_text_extractable(None, "image.png") is False

    def test_binary_unknown_extension_returns_false(self):
        assert is_text_extractable(None, "archive.xyz123") is False


# ===========================================================================
# ContentExtractorFactory.get_extractor()
# ===========================================================================


class TestContentExtractorFactoryGetExtractor:
    """Tests for ContentExtractorFactory.get_extractor()."""

    def test_returns_text_extractor_for_text_plain(self):
        extractor = ContentExtractorFactory.get_extractor("text/plain", "file.txt")
        assert isinstance(extractor, TextExtractor)

    def test_returns_markdown_extractor_for_text_markdown(self):
        extractor = ContentExtractorFactory.get_extractor("text/markdown", "notes.md")
        assert isinstance(extractor, MarkdownExtractor)

    def test_returns_json_extractor_for_application_json(self):
        extractor = ContentExtractorFactory.get_extractor("application/json", "data.json")
        assert isinstance(extractor, JSONExtractor)

    def test_returns_csv_extractor_for_text_csv(self):
        extractor = ContentExtractorFactory.get_extractor("text/csv", "report.csv")
        assert isinstance(extractor, CSVExtractor)

    def test_returns_xml_extractor_for_text_xml(self):
        extractor = ContentExtractorFactory.get_extractor("text/xml", "feed.xml")
        assert isinstance(extractor, XMLExtractor)

    def test_returns_code_extractor_for_text_x_python(self):
        extractor = ContentExtractorFactory.get_extractor("text/x-python", "script.py")
        assert isinstance(extractor, CodeExtractor)

    # --- extension-based fallback ---

    def test_returns_text_extractor_for_txt_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "readme.txt")
        assert isinstance(extractor, TextExtractor)

    def test_returns_markdown_extractor_for_md_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "notes.md")
        assert isinstance(extractor, MarkdownExtractor)

    def test_returns_code_extractor_for_py_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "app.py")
        assert isinstance(extractor, CodeExtractor)

    def test_returns_json_extractor_for_json_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "data.json")
        assert isinstance(extractor, JSONExtractor)

    def test_returns_csv_extractor_for_csv_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "report.csv")
        assert isinstance(extractor, CSVExtractor)

    def test_returns_xml_extractor_for_xml_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "config.xml")
        assert isinstance(extractor, XMLExtractor)

    def test_returns_none_for_unknown_type(self):
        extractor = ContentExtractorFactory.get_extractor("application/octet-stream", "file.bin")
        assert extractor is None

    def test_returns_none_for_none_type_and_unknown_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "archive.xyz")
        assert extractor is None

    def test_mime_type_takes_priority_over_extension(self):
        # Even though extension is .txt, the MIME type says JSON → JSONExtractor wins.
        extractor = ContentExtractorFactory.get_extractor("application/json", "notes.txt")
        assert isinstance(extractor, JSONExtractor)

    def test_returns_code_extractor_for_ts_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "component.ts")
        assert isinstance(extractor, CodeExtractor)

    def test_returns_code_extractor_for_jsx_extension(self):
        extractor = ContentExtractorFactory.get_extractor(None, "app.jsx")
        assert isinstance(extractor, CodeExtractor)


# ===========================================================================
# ContentExtractorFactory.extract_content()
# ===========================================================================


class TestContentExtractorFactoryExtractContent:
    """Tests for ContentExtractorFactory.extract_content()."""

    def test_extracts_content_from_text_file(self):
        data = b"Hello, world!"
        result = ContentExtractorFactory.extract_content(
            _make_file(data), "text/plain", "hello.txt"
        )
        assert result == "Hello, world!"

    def test_extracts_json_content(self):
        data = b'{"key": "value"}'
        result = ContentExtractorFactory.extract_content(
            _make_file(data), "application/json", "data.json"
        )
        assert result is not None
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_returns_none_when_no_extractor_found(self):
        data = b"\x00\x01\x02\x03"
        result = ContentExtractorFactory.extract_content(
            _make_file(data), "application/octet-stream", "binary.bin"
        )
        assert result is None

    def test_falls_back_to_extension_when_content_type_is_none(self):
        data = b"some,csv,data\n1,2,3\n"
        result = ContentExtractorFactory.extract_content(_make_file(data), None, "report.csv")
        assert result is not None
        assert "some" in result


# ===========================================================================
# TextExtractor.extract()
# ===========================================================================


class TestTextExtractor:
    """Tests for TextExtractor.extract()."""

    def test_extracts_utf8_text(self):
        content = "Hello, World!\nSecond line."
        extractor = TextExtractor()
        result = extractor.extract(_make_file(content.encode("utf-8")))
        assert result == content

    def test_extracts_unicode_text(self):
        content = "Ünïcödé tëxt"
        extractor = TextExtractor()
        result = extractor.extract(_make_file(content.encode("utf-8")))
        assert result == content

    def test_handles_seek_to_start(self):
        """Ensures extract() seeks to position 0 even if file was already read."""
        f = _make_file(b"data")
        f.read()  # advance position past EOF
        extractor = TextExtractor()
        result = extractor.extract(f)
        assert result == "data"

    def test_returns_empty_string_for_empty_file(self):
        extractor = TextExtractor()
        result = extractor.extract(_make_file(b""))
        assert result == ""

    def test_ignores_invalid_utf8_bytes(self):
        # b"\xff\xfe" is not valid UTF-8 but should be replaced silently.
        extractor = TextExtractor()
        result = extractor.extract(_make_file(b"hello\xff\xfethere"))
        assert result is not None
        assert "hello" in result
        assert "there" in result


# ===========================================================================
# MarkdownExtractor.extract()
# ===========================================================================


class TestMarkdownExtractor:
    """Tests for MarkdownExtractor.extract()."""

    def test_extracts_markdown_headings(self):
        md = "# Heading\n\nParagraph text.\n\n## Sub-heading\n"
        extractor = MarkdownExtractor()
        result = extractor.extract(_make_file(md.encode("utf-8")))
        assert result == md

    def test_extracts_markdown_with_code_blocks(self):
        md = "```python\nprint('hello')\n```\n"
        extractor = MarkdownExtractor()
        result = extractor.extract(_make_file(md.encode("utf-8")))
        assert result == md

    def test_returns_empty_string_for_empty_file(self):
        extractor = MarkdownExtractor()
        result = extractor.extract(_make_file(b""))
        assert result == ""

    def test_seeks_to_start_automatically(self):
        f = _make_file(b"# Title\n")
        f.read()
        extractor = MarkdownExtractor()
        result = extractor.extract(f)
        assert "Title" in result


# ===========================================================================
# CodeExtractor.extract()
# ===========================================================================


class TestCodeExtractor:
    """Tests for CodeExtractor.extract()."""

    def test_extracts_utf8_python_code(self):
        code = "def hello():\n    return 'world'\n"
        extractor = CodeExtractor()
        result = extractor.extract(_make_file(code.encode("utf-8")))
        assert result == code

    def test_falls_back_to_latin1_when_utf8_fails(self):
        # latin-1 byte that is invalid UTF-8.
        content = b"caf\xe9"
        extractor = CodeExtractor()
        result = extractor.extract(_make_file(content))
        assert result is not None
        assert "caf" in result

    def test_extracts_multiline_code(self):
        code = "for i in range(10):\n    print(i)\n"
        extractor = CodeExtractor()
        result = extractor.extract(_make_file(code.encode("utf-8")))
        assert "range(10)" in result

    def test_seeks_to_start_automatically(self):
        f = _make_file(b"x = 1\n")
        f.read()
        extractor = CodeExtractor()
        result = extractor.extract(f)
        assert "x = 1" in result

    def test_returns_empty_string_for_empty_file(self):
        extractor = CodeExtractor()
        result = extractor.extract(_make_file(b""))
        assert result == ""


# ===========================================================================
# JSONExtractor.extract()
# ===========================================================================


class TestJSONExtractor:
    """Tests for JSONExtractor.extract()."""

    def test_valid_json_is_pretty_printed(self):
        data = b'{"a":1,"b":"two"}'
        extractor = JSONExtractor()
        result = extractor.extract(_make_file(data))
        assert result is not None
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": "two"}
        # Pretty-printed JSON will have newlines.
        assert "\n" in result

    def test_valid_nested_json(self):
        data = json.dumps({"outer": {"inner": [1, 2, 3]}}).encode()
        extractor = JSONExtractor()
        result = extractor.extract(_make_file(data))
        assert result is not None
        parsed = json.loads(result)
        assert parsed["outer"]["inner"] == [1, 2, 3]

    def test_invalid_json_returns_raw_content(self):
        raw = b"not valid json {{{}"
        extractor = JSONExtractor()
        result = extractor.extract(_make_file(raw))
        assert result is not None
        assert "not valid json" in result

    def test_empty_file_returns_raw_content_or_none(self):
        extractor = JSONExtractor()
        # Empty content is invalid JSON; it should return the raw (empty) string.
        result = extractor.extract(_make_file(b""))
        # Either raw empty string or None are acceptable graceful responses.
        assert result is None or result == ""

    def test_seeks_to_start_automatically(self):
        f = _make_file(b'{"key": "val"}')
        f.read()
        extractor = JSONExtractor()
        result = extractor.extract(f)
        assert result is not None
        assert "key" in result


# ===========================================================================
# CSVExtractor.extract()
# ===========================================================================


class TestCSVExtractor:
    """Tests for CSVExtractor.extract()."""

    def test_small_csv_produces_markdown_table(self):
        csv_data = b"Name,Age\nAlice,30\nBob,25\n"
        extractor = CSVExtractor()
        result = extractor.extract(_make_file(csv_data))
        assert result is not None
        # Header row should appear.
        assert "Name" in result
        assert "Age" in result
        # Separator row generated after header.
        assert "---" in result
        # Data rows.
        assert "Alice" in result
        assert "Bob" in result

    def test_single_row_csv(self):
        csv_data = b"col1,col2,col3\n"
        extractor = CSVExtractor()
        result = extractor.extract(_make_file(csv_data))
        assert result is not None
        assert "col1" in result

    def test_empty_csv_returns_none(self):
        extractor = CSVExtractor()
        result = extractor.extract(_make_file(b""))
        assert result is None

    def test_csv_with_quoted_fields(self):
        csv_data = b'"first name","last name"\n"John","Doe"\n'
        extractor = CSVExtractor()
        result = extractor.extract(_make_file(csv_data))
        assert result is not None
        assert "first name" in result or "John" in result

    def test_csv_uses_pipe_separator_in_output(self):
        csv_data = b"a,b\n1,2\n"
        extractor = CSVExtractor()
        result = extractor.extract(_make_file(csv_data))
        assert result is not None
        assert "|" in result


# ===========================================================================
# XMLExtractor.extract()
# ===========================================================================


class TestXMLExtractor:
    """Tests for XMLExtractor.extract()."""

    def test_valid_xml_is_pretty_printed(self):
        xml = b"<root><child>value</child></root>"
        extractor = XMLExtractor()
        result = extractor.extract(_make_file(xml))
        assert result is not None
        assert "child" in result
        assert "value" in result
        # minidom adds indentation / newlines.
        assert "\n" in result

    def test_valid_xml_with_attributes(self):
        xml = b'<items><item id="1">first</item><item id="2">second</item></items>'
        extractor = XMLExtractor()
        result = extractor.extract(_make_file(xml))
        assert result is not None
        assert "first" in result
        assert "second" in result

    def test_invalid_xml_returns_raw_content(self):
        bad_xml = b"<root><unclosed>"
        extractor = XMLExtractor()
        result = extractor.extract(_make_file(bad_xml))
        assert result is not None
        assert "root" in result or "unclosed" in result

    def test_empty_file_returns_raw_or_none(self):
        extractor = XMLExtractor()
        result = extractor.extract(_make_file(b""))
        # Graceful handling: either None or a raw empty-ish string.
        assert result is None or isinstance(result, str)

    def test_seeks_to_start_automatically(self):
        f = _make_file(b"<a>hello</a>")
        f.read()
        extractor = XMLExtractor()
        result = extractor.extract(f)
        assert result is not None
        assert "hello" in result


# ===========================================================================
# ProcessedFiles dataclass
# ===========================================================================


class TestProcessedFilesDataclass:
    """Tests for ProcessedFiles dataclass creation and field access."""

    def test_can_create_empty_processed_files(self):
        pf = ProcessedFiles(
            binary_parts=[],
            text_parts=[],
            large_file_ids=set(),
            large_file_info=[],
            skipped_files=[],
        )
        assert pf.binary_parts == []
        assert pf.text_parts == []
        assert pf.large_file_ids == set()
        assert pf.large_file_info == []
        assert pf.skipped_files == []

    def test_binary_parts_stores_list(self):
        pf = ProcessedFiles(
            binary_parts=["part1", "part2"],  # type: ignore[list-item]
            text_parts=[],
            large_file_ids=set(),
            large_file_info=[],
            skipped_files=[],
        )
        assert len(pf.binary_parts) == 2

    def test_large_file_ids_is_set(self):
        ids = {"id-1", "id-2", "id-3"}
        pf = ProcessedFiles(
            binary_parts=[],
            text_parts=[],
            large_file_ids=ids,
            large_file_info=[],
            skipped_files=[],
        )
        assert "id-1" in pf.large_file_ids
        assert len(pf.large_file_ids) == 3

    def test_skipped_files_stores_dicts(self):
        skipped = [{"file_name": "bad.bin", "reason": "Unsupported type"}]
        pf = ProcessedFiles(
            binary_parts=[],
            text_parts=[],
            large_file_ids=set(),
            large_file_info=[],
            skipped_files=skipped,
        )
        assert pf.skipped_files[0]["file_name"] == "bad.bin"


# ===========================================================================
# estimate_tokens
# ===========================================================================


class TestEstimateTokens:
    """Tests for estimate_tokens pure utility function."""

    def test_empty_string_returns_zero(self):
        from ii_agent.chat.application.file_processor import estimate_tokens
        assert estimate_tokens("") == 0

    def test_three_chars_returns_one_token(self):
        from ii_agent.chat.application.file_processor import estimate_tokens
        # CHARS_PER_TOKEN = 3, so 3 chars = ceil(3/3) = 1
        assert estimate_tokens("abc") == 1

    def test_four_chars_rounds_up(self):
        from ii_agent.chat.application.file_processor import estimate_tokens
        # 4 chars → ceil(4/3) = 2
        assert estimate_tokens("abcd") == 2

    def test_nine_chars_returns_three(self):
        from ii_agent.chat.application.file_processor import estimate_tokens
        assert estimate_tokens("a" * 9) == 3

    def test_longer_text_estimates_reasonably(self):
        from ii_agent.chat.application.file_processor import estimate_tokens
        text = "Hello world! " * 100  # 1300 chars → ceil(1300/3) = 434
        result = estimate_tokens(text)
        assert result > 100


# ===========================================================================
# get_pdf_page_count / extract_pdf_text
# ===========================================================================


class TestPdfFunctions:
    """Tests for get_pdf_page_count and extract_pdf_text."""

    def _make_pdf_bytes(self) -> bytes:
        """Return a minimal valid PDF bytes object using PyMuPDF."""
        try:
            import fitz

            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Hello, PDF world!")
            return doc.tobytes()
        except ImportError:
            pytest.skip("PyMuPDF not installed")

    def test_get_pdf_page_count_valid(self):
        from ii_agent.chat.application.file_processor import get_pdf_page_count
        pdf_bytes = self._make_pdf_bytes()
        count = get_pdf_page_count(pdf_bytes)
        assert count == 1

    def test_get_pdf_page_count_invalid_returns_minus_one(self):
        from ii_agent.chat.application.file_processor import get_pdf_page_count
        result = get_pdf_page_count(b"not a pdf at all")
        assert result == -1

    def test_extract_pdf_text_returns_content(self):
        from ii_agent.chat.application.file_processor import extract_pdf_text
        pdf_bytes = self._make_pdf_bytes()
        text = extract_pdf_text(pdf_bytes)
        assert text is not None
        assert "Hello" in text

    def test_extract_pdf_text_invalid_returns_none(self):
        from ii_agent.chat.application.file_processor import extract_pdf_text
        result = extract_pdf_text(b"definitely not pdf bytes")
        assert result is None
