# tests/test_schema.py
"""
Schema validation tests for parsed LCHA structure.
Ensures all nodes have required fields per schema v2.1.
"""

import pytest
import json
from pathlib import Path

REQUIRED_NODE_FIELDS = ["id", "parent_id", "type", "text_for_embedding", "references"]
REQUIRED_PART_FIELDS = REQUIRED_NODE_FIELDS + ["number", "title", "sections"]
REQUIRED_SECTION_FIELDS = REQUIRED_NODE_FIELDS + ["section_number", "parsed", "raw_text"]
REQUIRED_DEFINITION_FIELDS = REQUIRED_NODE_FIELDS + ["classification", "term", "parsed", "raw_text"]


class TestSchemaCompliance:
    """Test that all nodes comply with schema v2.1"""

    def test_structure_has_metadata(self, lcha_structure):
        assert "metadata" in lcha_structure
        assert "schema_version" in lcha_structure["metadata"]

    def test_structure_has_parts(self, lcha_structure):
        assert "parts" in lcha_structure
        assert isinstance(lcha_structure["parts"], dict), "parts should be dict, not list"

    def test_all_parts_have_required_fields(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            for field in REQUIRED_PART_FIELDS:
                assert field in part_data, \
                    f"Part {part_num} missing required field: {field}"

    def test_all_sections_have_required_fields(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            for section_num, section_data in part_data.get("sections", {}).items():
                for field in REQUIRED_SECTION_FIELDS:
                    assert field in section_data, \
                        f"Part {part_num} Section {section_num} missing field: {field}"

    def test_all_definitions_have_required_fields(self, lcha_structure):
        definitions = lcha_structure["parts"].get("1", {}).get("sections", {}).get("1.1", {}).get("definitions", {})

        for term, def_data in definitions.items():
            for field in REQUIRED_DEFINITION_FIELDS:
                assert field in def_data, \
                    f"Definition '{term}' missing required field: {field}"


class TestNodeIdIntegrity:
    """Test that node IDs are valid and consistent"""

    def test_part_ids_match_pattern(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            expected_id = f"part{part_num}"
            assert part_data["id"] == expected_id, \
                f"Part {part_num} has incorrect id: {part_data['id']}"

    def test_section_ids_match_pattern(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            for section_num, section_data in part_data.get("sections", {}).items():
                section_id = section_data["id"]
                assert section_id.startswith(f"part{part_num}.s"), \
                    f"Section {section_num} has incorrect id prefix: {section_id}"

    def test_definition_ids_match_pattern(self, lcha_structure):
        definitions = lcha_structure["parts"].get("1", {}).get("sections", {}).get("1.1", {}).get("definitions", {})

        for term, def_data in definitions.items():
            def_id = def_data["id"]
            assert def_id.startswith("part1.s1_1.def."), \
                f"Definition '{term}' has incorrect id prefix: {def_id}"

    def test_no_duplicate_ids(self, lcha_structure):
        """Collect all IDs and check for duplicates"""
        all_ids = []

        for part_num, part_data in lcha_structure["parts"].items():
            all_ids.append(part_data["id"])

            for section_num, section_data in part_data.get("sections", {}).items():
                all_ids.append(section_data["id"])

                for term, def_data in section_data.get("definitions", {}).items():
                    all_ids.append(def_data["id"])

        duplicates = [id for id in all_ids if all_ids.count(id) > 1]
        assert len(duplicates) == 0, f"Duplicate IDs found: {set(duplicates)}"


class TestParentIdIntegrity:
    """Test that parent_id references are valid"""

    def test_parts_have_null_parent(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            assert part_data["parent_id"] is None, \
                f"Part {part_num} should have null parent_id"

    def test_sections_reference_valid_parent(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            part_id = part_data["id"]

            for section_num, section_data in part_data.get("sections", {}).items():
                assert section_data["parent_id"] == part_id, \
                    f"Section {section_num} has incorrect parent_id"

    def test_definitions_reference_valid_parent(self, lcha_structure):
        part1 = lcha_structure["parts"].get("1", {})
        section_1_1 = part1.get("sections", {}).get("1.1", {})
        section_id = section_1_1.get("id")

        for term, def_data in section_1_1.get("definitions", {}).items():
            assert def_data["parent_id"] == section_id, \
                f"Definition '{term}' has incorrect parent_id"


class TestTextForEmbedding:
    """Test that text_for_embedding fields are valid"""

    def test_text_for_embedding_not_empty(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            assert len(part_data["text_for_embedding"]) > 0, \
                f"Part {part_num} has empty text_for_embedding"

    def test_text_for_embedding_no_newlines(self, lcha_structure):
        """text_for_embedding should be single line for vector embedding"""
        definitions = lcha_structure["parts"].get("1", {}).get("sections", {}).get("1.1", {}).get("definitions", {})

        for term, def_data in list(definitions.items())[:50]:  # Sample first 50
            text = def_data["text_for_embedding"]
            assert "\n" not in text, \
                f"Definition '{term}' has newline in text_for_embedding"

    def test_text_for_embedding_no_artifacts(self, lcha_structure):
        """text_for_embedding should not contain page footers"""
        definitions = lcha_structure["parts"].get("1", {}).get("sections", {}).get("1.1", {}).get("definitions", {})

        for term, def_data in definitions.items():
            text = def_data["text_for_embedding"]
            assert "DRAFT: August 2023" not in text, \
                f"Definition '{term}' has footer artifact in text_for_embedding"


class TestReferencesArray:
    """Test that references arrays are valid"""

    def test_references_is_list(self, lcha_structure):
        for part_num, part_data in lcha_structure["parts"].items():
            for section_num, section_data in part_data.get("sections", {}).items():
                refs = section_data.get("references", [])
                assert isinstance(refs, list), \
                    f"Section {section_num} references should be list"

    def test_references_have_type_and_target(self, lcha_structure):
        definitions = lcha_structure["parts"].get("1", {}).get("sections", {}).get("1.1", {}).get("definitions", {})

        for term, def_data in definitions.items():
            for ref in def_data.get("references", []):
                assert "type" in ref, f"Reference in '{term}' missing 'type'"
                assert "target" in ref, f"Reference in '{term}' missing 'target'"
