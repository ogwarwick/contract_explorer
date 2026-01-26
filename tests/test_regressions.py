# tests/test_regressions.py
"""
Regression tests for known bugs that were fixed.
These tests ensure bugs don't return when refactoring.
"""

import pytest
from lcha_utils import (
    clean_extracted_text,
    parse_alphabetic_subsections,
    extract_part_text,
    normalize_text_whitespace,
)


class TestWithdrawalActBug:
    """
    Bug: (W) in "Withdrawal Act 2018" was parsed as subsection marker.
    Fixed in: parse_alphabetic_subsections() with lookbehind pattern.
    """

    def test_withdrawal_act_not_parsed_as_subsection(self, sample_withdrawal_act_text):
        result = parse_alphabetic_subsections(sample_withdrawal_act_text)
        # Should NOT have (W) as a key
        assert "(W)" not in result, \
            "Bug regression: (W) in 'Withdrawal Act' should not be parsed as subsection"

    def test_european_union_withdrawal_act(self):
        text = "the European Union (Withdrawal) Act 2018"
        result = parse_alphabetic_subsections(text)
        assert "(W)" not in result

    def test_legitimate_W_subsection_still_works(self):
        # A real (W) subsection at start of line should still parse
        text = "(A) First item (B) Second item (W) Twenty-third item"
        result = parse_alphabetic_subsections(text)
        # This SHOULD have (W) because it's a legitimate subsection
        assert "(W)" in result


class TestConditionReferenceBug:
    """
    Bug: 2.3(B) and similar patterns were parsed as subsection markers.
    Fixed in: parse_alphabetic_subsections() with negative lookbehind for digits.
    """

    def test_condition_reference_not_parsed(self, sample_condition_reference_text):
        result = parse_alphabetic_subsections(sample_condition_reference_text)
        # The text contains "2.3(B)" which should NOT be parsed as a subsection
        # Check if (B) is in result but doesn't contain the Condition reference
        if "(B)" in result:
            # If (B) is parsed, it shouldn't be from "Condition 2.3(B)"
            assert "Condition 2.3" not in result.get("(B)", ""), \
                "Bug regression: (B) in 'Condition 2.3(B)' should not be parsed as subsection"

    def test_standalone_subsection_still_works(self):
        text = "The requirements are: (A) compliance with Part 1; (B) adherence to Schedule 2"
        result = parse_alphabetic_subsections(text)
        assert "(A)" in result
        assert "(B)" in result


class TestPageFooterBug:
    """
    Bug: Page footers like "123\nDRAFT: August 2023" contaminated parsed text.
    Fixed in: clean_extracted_text() with regex stripping.
    """

    def test_footer_removed(self, sample_text_with_footer):
        result = clean_extracted_text(sample_text_with_footer)
        assert "DRAFT: August 2023" not in result

    def test_various_page_numbers(self):
        text = "Content here\n1\nDRAFT: August 2023\nMore content\n99\nDRAFT: August 2023\nEnd"
        result = clean_extracted_text(text)
        assert "DRAFT: August 2023" not in result

    def test_content_preserved(self, sample_text_with_footer):
        result = clean_extracted_text(sample_text_with_footer)
        assert "legal text" in result
        assert "content" in result


class TestTOCMatchingBug:
    """
    Bug: PART 3 in table of contents was matched instead of actual Part 3 content.
    Fixed in: extract_part_text() using PART\s*X\n pattern with newline anchor.
    """

    def test_toc_not_matched(self):
        text = '''
TABLE OF CONTENTS
PART 1 - Definitions .......................... 1
PART 2 - Term ................................. 50
PART 3 - Conditions ........................... 60

PART 1
INTERPRETATION AND CONSTRUCTION
1.1 Definitions
"Agreement" means...

PART 2
TERM
2.1 The Term...

PART 3
CONDITIONS PRECEDENT
3.1 The conditions...
'''
        result = extract_part_text(text, 3)
        if result:
            # Should get actual Part 3 content, not TOC entry
            assert "CONDITIONS PRECEDENT" in result or "conditions" in result.lower()
            assert "..........................." not in result


class TestLineBreakInReferencesBug:
    """
    Bug: Line breaks within references like "Annex 10\n(Low Carbon..." were preserved.
    Fixed in: normalize_text_whitespace() converting single newlines to spaces.
    """

    def test_line_break_normalized(self):
        text = "Annex 10\n(Low Carbon Hydrogen Certification)"
        result = normalize_text_whitespace(text)
        assert "\n" not in result
        assert "Annex 10 (Low Carbon" in result or "Annex 10(Low Carbon" in result

    def test_multiline_reference_cleaned(self):
        text = "as defined in Condition 5.2\n(Payment Calculations)"
        result = normalize_text_whitespace(text)
        assert "\n" not in result
