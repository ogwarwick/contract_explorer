# tests/test_parts.py
"""
Integration tests for parsed parts.
Tests expected counts and structure for each part.
"""

import pytest


class TestPart1:
    """Integration tests for Part 1: Definitions"""

    def test_part1_exists(self, lcha_structure):
        assert "1" in lcha_structure["parts"]

    def test_part1_title(self, lcha_structure):
        part1 = lcha_structure["parts"]["1"]
        assert "INTERPRETATION" in part1["title"].upper()

    def test_part1_has_definitions_section(self, lcha_structure):
        part1 = lcha_structure["parts"]["1"]
        assert "1.1" in part1["sections"]
        assert "definitions" in part1["sections"]["1.1"]

    def test_part1_definition_count_reasonable(self, lcha_structure):
        definitions = lcha_structure["parts"]["1"]["sections"]["1.1"]["definitions"]
        count = len(definitions)
        # Should have hundreds of definitions, not thousands (which would suggest duplicates)
        assert 500 < count < 1500, f"Unexpected definition count: {count}"

    def test_part1_sections_range(self, lcha_structure):
        sections = lcha_structure["parts"]["1"]["sections"]
        # Part 1 should have sections 1.1 through 1.15
        assert "1.1" in sections
        assert "1.2" in sections


class TestPart2:
    """Integration tests for Part 2: Term"""

    def test_part2_exists(self, lcha_structure):
        assert "2" in lcha_structure["parts"]

    def test_part2_title(self, lcha_structure):
        part2 = lcha_structure["parts"]["2"]
        assert "TERM" in part2["title"].upper()

    def test_part2_sections_range(self, lcha_structure):
        sections = lcha_structure["parts"]["2"]["sections"]
        # Part 2 should have sections 2.1-2.4
        assert "2.1" in sections


class TestPart3:
    """Integration tests for Part 3: Conditions Precedent"""

    def test_part3_exists(self, lcha_structure):
        assert "3" in lcha_structure["parts"]

    def test_part3_has_sections(self, lcha_structure):
        sections = lcha_structure["parts"]["3"]["sections"]
        assert len(sections) > 0


class TestPart4:
    """Integration tests for Part 4"""

    def test_part4_exists(self, lcha_structure):
        assert "4" in lcha_structure["parts"]

    def test_part4_has_sections(self, lcha_structure):
        sections = lcha_structure["parts"]["4"]["sections"]
        assert len(sections) > 0


class TestPart5:
    """Integration tests for Part 5"""

    def test_part5_exists(self, lcha_structure):
        assert "5" in lcha_structure["parts"]

    def test_part5_has_sections(self, lcha_structure):
        sections = lcha_structure["parts"]["5"]["sections"]
        assert len(sections) > 0


class TestPart6:
    """Integration tests for Part 6"""

    def test_part6_exists(self, lcha_structure):
        assert "6" in lcha_structure["parts"]

    def test_part6_has_sections(self, lcha_structure):
        sections = lcha_structure["parts"]["6"]["sections"]
        assert len(sections) > 0

    def test_part6_sections_have_required_fields(self, lcha_structure):
        sections = lcha_structure["parts"]["6"]["sections"]
        for section_num, section_data in sections.items():
            assert "id" in section_data
            assert "parent_id" in section_data
            assert "text_for_embedding" in section_data
            assert "references" in section_data
            assert "parsed" in section_data


class TestPart7:
    """Integration tests for Part 7"""

    def test_part7_exists(self, lcha_structure):
        assert "7" in lcha_structure["parts"]

    def test_part7_has_sections(self, lcha_structure):
        sections = lcha_structure["parts"]["7"]["sections"]
        assert len(sections) > 0

    def test_part7_sections_have_required_fields(self, lcha_structure):
        sections = lcha_structure["parts"]["7"]["sections"]
        required = ["id", "parent_id", "type", "text_for_embedding", "references"]
        for section_id, section_data in sections.items():
            for field in required:
                assert field in section_data, f"Section {section_id} missing {field}"


class TestPart8:
    """Integration tests for Part 8"""

    def test_part8_exists(self, lcha_structure):
        assert "8" in lcha_structure["parts"]

    def test_part8_has_sections(self, lcha_structure):
        sections = lcha_structure["parts"]["8"]["sections"]
        assert len(sections) > 0

    def test_part8_sections_have_required_fields(self, lcha_structure):
        sections = lcha_structure["parts"]["8"]["sections"]
        required = ["id", "parent_id", "type", "text_for_embedding", "references"]
        for section_id, section_data in sections.items():
            for field in required:
                assert field in section_data, f"Section {section_id} missing {field}"


class TestAllParts:
    """Cross-part integration tests"""

    def test_parsed_parts_count(self, lcha_structure):
        """Should have 8 parts parsed so far"""
        assert len(lcha_structure["parts"]) >= 8

    def test_total_sections_reasonable(self, lcha_structure):
        """Total sections should be in expected range"""
        total = sum(
            len(part["sections"])
            for part in lcha_structure["parts"].values()
        )
        assert total > 100, f"Too few sections: {total}"
        assert total < 500, f"Too many sections: {total}"

    def test_no_empty_parts(self, lcha_structure):
        """No part should have zero sections"""
        for part_num, part_data in lcha_structure["parts"].items():
            assert len(part_data["sections"]) > 0, \
                f"Part {part_num} has no sections"
