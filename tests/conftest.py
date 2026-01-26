# tests/conftest.py
"""Shared test fixtures for LCHA parser tests"""

import json
import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lcha_utils import (
    clean_extracted_text,
    normalize_text_whitespace,
    clean_text_for_embedding,
    extract_references,
    parse_alphabetic_subsections,
    parse_roman_subsections,
    parse_lowercase_subsections,
    parse_nested_subsections,
    slugify,
)


@pytest.fixture
def sample_definition_simple():
    """Simple definition without subsections"""
    return '"Agreement" means this agreement between the Producer and the LCHA Counterparty'


@pytest.fixture
def sample_definition_with_subsections():
    """Definition with (A), (B) subsections"""
    return '''"Acceptable Collateral" means: (A) a Letter of Credit; and/or (B) a cash amount (expressed in pounds (£)) transferred to the credit of a Reserve Account'''


@pytest.fixture
def sample_definition_nested():
    """Definition with (A)(i)(a) nesting"""
    return '''"Complex Term" means: (A) the first category: (i) sub-item one; (ii) sub-item two; and (B) the second category'''


@pytest.fixture
def sample_text_with_footer():
    """Text contaminated with page footer"""
    return '''This is some legal text that continues across
123
DRAFT: August 2023
multiple pages with content here.'''


@pytest.fixture
def sample_text_with_references():
    """Text containing cross-references"""
    return '''as defined in Condition 5.2 and further described in Annex 10 (Low Carbon Hydrogen Certification) and Part 3 of Schedule 2'''


@pytest.fixture
def sample_withdrawal_act_text():
    """Text with (W) that should NOT be parsed as subsection"""
    return '''References to the Withdrawal Act 2018 or the European Union (Withdrawal) Act 2018 shall be construed accordingly.'''


@pytest.fixture
def sample_condition_reference_text():
    """Text with 2.3(B) pattern that should NOT be parsed as subsection"""
    return '''As set out in Condition 2.3(B) and Condition 5.1(A), the Producer shall comply with all requirements.'''


@pytest.fixture
def lcha_structure():
    """Load the actual parsed structure"""
    structure_path = Path(__file__).parent.parent / "lcha_structure.json"
    if structure_path.exists():
        with open(structure_path) as f:
            return json.load(f)
    pytest.skip("lcha_structure.json not found")


@pytest.fixture
def part1_definitions(lcha_structure):
    """Extract Part 1 definitions from structure"""
    try:
        return lcha_structure["parts"]["1"]["sections"]["1.1"]["definitions"]
    except KeyError:
        pytest.skip("Part 1 definitions not found in structure")
