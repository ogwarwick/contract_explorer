# tests/test_utils.py
"""Unit tests for lcha_utils.py helper functions"""

import pytest
from lcha_utils import (
    clean_extracted_text,
    normalize_text_whitespace,
    clean_text_for_embedding,
    extract_references,
    parse_alphabetic_subsections,
    parse_roman_subsections,
    parse_lowercase_subsections,
    slugify,
)


class TestCleanExtractedText:
    """Tests for clean_extracted_text()"""

    def test_removes_page_footer(self, sample_text_with_footer):
        result = clean_extracted_text(sample_text_with_footer)
        assert "DRAFT: August 2023" not in result

    def test_preserves_content(self):
        text = "This is important legal content."
        result = clean_extracted_text(text)
        assert "important legal content" in result

    def test_handles_multiple_footers(self):
        text = "Page one content\n45\nDRAFT: August 2023\nPage two\n46\nDRAFT: August 2023\nEnd"
        result = clean_extracted_text(text)
        assert result.count("DRAFT: August 2023") == 0


class TestNormalizeTextWhitespace:
    """Tests for normalize_text_whitespace()"""

    def test_single_newline_to_space(self):
        text = "Line one\nLine two"
        result = normalize_text_whitespace(text)
        assert result == "Line one Line two"

    def test_collapses_multiple_spaces(self):
        text = "Too    many     spaces"
        result = normalize_text_whitespace(text)
        assert "    " not in result

    def test_strips_leading_trailing(self):
        text = "  content  "
        result = normalize_text_whitespace(text)
        assert result == "content"


class TestCleanTextForEmbedding:
    """Tests for clean_text_for_embedding()"""

    def test_returns_single_line(self):
        text = "Line one\nLine two\nLine three"
        result = clean_text_for_embedding(text)
        assert "\n" not in result

    def test_removes_artifacts(self, sample_text_with_footer):
        result = clean_text_for_embedding(sample_text_with_footer)
        assert "DRAFT: August 2023" not in result

    def test_not_empty(self):
        text = "Some content"
        result = clean_text_for_embedding(text)
        assert len(result) > 0


class TestExtractReferences:
    """Tests for extract_references()"""

    def test_extracts_condition_reference(self):
        text = "as defined in Condition 5.2"
        refs = extract_references(text)
        assert any(r["type"] == "condition" and "5.2" in r["target"] for r in refs)

    def test_extracts_annex_reference(self):
        text = "see Annex 10 for details"
        refs = extract_references(text)
        assert any(r["type"] == "annex" and "10" in r["target"] for r in refs)

    def test_extracts_part_reference(self):
        text = "as set out in Part 3"
        refs = extract_references(text)
        assert any(r["type"] == "part" and "3" in r["target"] for r in refs)

    def test_extracts_schedule_reference(self):
        text = "Schedule 2 contains"
        refs = extract_references(text)
        assert any(r["type"] == "schedule" and "2" in r["target"] for r in refs)

    def test_extracts_multiple_references(self, sample_text_with_references):
        refs = extract_references(sample_text_with_references)
        types = {r["type"] for r in refs}
        assert "condition" in types
        assert "annex" in types

    def test_deduplicates_references(self):
        text = "Condition 5.2 and again Condition 5.2"
        refs = extract_references(text)
        condition_refs = [r for r in refs if r["target"] == "Condition 5.2"]
        assert len(condition_refs) == 1

    def test_empty_text_returns_empty_list(self):
        refs = extract_references("")
        assert refs == []


class TestParseAlphabeticSubsections:
    """Tests for parse_alphabetic_subsections()"""

    def test_parses_simple_subsections(self):
        text = "(A) First item (B) Second item (C) Third item"
        result = parse_alphabetic_subsections(text)
        assert "(A)" in result
        assert "(B)" in result
        assert "(C)" in result

    def test_content_extracted_correctly(self):
        text = "(A) The first category includes all items (B) The second category"
        result = parse_alphabetic_subsections(text)
        assert "first category" in result.get("(A)", "")

    def test_handles_multiline(self):
        text = "(A) First item that\nspans multiple lines (B) Second item"
        result = parse_alphabetic_subsections(text)
        assert "(A)" in result
        assert "(B)" in result


class TestParseRomanSubsections:
    """Tests for parse_roman_subsections()"""

    def test_parses_roman_numerals(self):
        text = "(i) First (ii) Second (iii) Third"
        result = parse_roman_subsections(text)
        assert "(i)" in result
        assert "(ii)" in result
        assert "(iii)" in result

    def test_handles_higher_numerals(self):
        text = "(iv) Fourth (v) Fifth (vi) Sixth"
        result = parse_roman_subsections(text)
        assert "(iv)" in result
        assert "(v)" in result


class TestParseLowercaseSubsections:
    """Tests for parse_lowercase_subsections()"""

    def test_parses_lowercase_letters(self):
        text = "(a) First (b) Second (c) Third"
        result = parse_lowercase_subsections(text)
        assert "(a)" in result
        assert "(b)" in result
        assert "(c)" in result


class TestSlugify:
    """Tests for slugify()"""

    def test_basic_slugify(self):
        assert slugify("Hello World") == "Hello_World"

    def test_removes_special_chars(self):
        result = slugify("Term (with) special-chars!")
        assert "(" not in result
        assert ")" not in result
        assert "-" not in result
        assert "!" not in result

    def test_handles_spaces(self):
        result = slugify("Multiple   Spaces   Here")
        assert "   " not in result

    def test_strips_underscores(self):
        result = slugify("  Leading and trailing  ")
        assert not result.startswith("_")
        assert not result.endswith("_")
