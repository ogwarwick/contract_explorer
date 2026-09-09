import re
from typing import Dict, List, Tuple

class ParserConfig:
    def __init__(self, name: str):
        self.name = name
        
        # Main Body Patterns (No definition patterns to avoid false matches)
        if "FINAL_CFD_Standard_Terms_and_Conditions_V2" in name:
            self.patterns_main_body: List[Tuple[str, re.Pattern]] = [
                ("part",                    re.compile(r"^Part\s+\d+[A-Z]?\b")),
                ("condition",               re.compile(r"^\d+[A-Z]?\.(?:\s|$)")),
                ("clause",                  re.compile(r"^\d+[A-Z]?\.\d+[A-Z]?(?:\s|$)")),
                ("sub_clause",              re.compile(r"^\((?!\))(?:x{0,3})(?:ix|iv|v?i{0,3})\)")),
                ("sub_sub_clause",          re.compile(r"^\([a-z]{1,2}\)")),
                ("sub_sub_sub_clause",      re.compile(r"^\([0-9]+\)")),
                ("subtitle",                re.compile(r"^[A-Z][A-Z0-9 &,\-]{8,60}$")),
            ]
        else:
            self.patterns_main_body: List[Tuple[str, re.Pattern]] = [
                ("part",                    re.compile(r"^Part\s+\d+[A-Z]?\b")),
                ("condition",               re.compile(r"^\d+[A-Z]?\.(?:\s|$)")),
                ("clause",                  re.compile(r"^\d+[A-Z]?\.\d+[A-Z]?(?:\s|$)")),
                ("sub_clause",              re.compile(r"^\([A-Z]\)")),
                ("sub_sub_clause",          re.compile(r"^\((?!\))(?:x{0,3})(?:ix|iv|v?i{0,3})\)")),
                ("sub_sub_sub_clause",      re.compile(r"^\([a-z]{1,2}\)")),
                ("sub_sub_sub_sub_clause",  re.compile(r"^\([0-9]+\)")),
                ("subtitle",                re.compile(r"^[A-Z][A-Z0-9 &,\-]{8,60}$")),
            ]
        
        self.depth_main_body: Dict[str, int] = {
            "part": 0, "part_title": 1, "condition": 2, "condition_subtitle": 3,
            "clause": 4, "sub_clause": 5, "sub_sub_clause": 6, "sub_sub_sub_clause": 7, "sub_sub_sub_sub_clause": 8, "annex": 0,
        }

        # Definition Patterns — includes enumerator hierarchy for nested lists
        self.patterns_definitions: List[Tuple[str, re.Pattern]] = [
            ("part",      re.compile(r"^Part\s+\d+[A-Z]?\b")),
            ("condition", re.compile(r"^\d+[A-Z]?\.(?:\s|$)")),
            ("definition", re.compile(
                r'^(?:"\s*[^"\n]{2,80}?\s*"'
                r'|\u201c\s*[^\u201d\n]{2,80}?\s*\u201d'
                r"|'\s*[^'\n]{2,80}?\s*'"
                r'|\u2018\s*[^\u2019\n]{2,80}?\s*\u2019)'
                r'\s*\d*[A-Z]?\s*'
                r'(?:means|has\s+the\s+meaning|shall\s+have|shall\s+mean|is\b|or\b'
                r'|Condition\b|paragraph\b|Annex\b|Schedule\b|Appendix\b|Part\b|formula\b|term\b)',
                re.IGNORECASE)),
            ("definition", re.compile(
                r"^['\"\u201c\u2018]\s*"
                r"[a-z0-9\s&-]{2,80}"  # Term name
                r"\s*['\"\u201d\u2019]?\s*"  # Optional closing quote
                r"(?:Condition|paragraph|Annex|Schedule|Appendix|Part|means|has\s+the\s+meaning|shall\s+have|shall\s+mean|is\b)"
                r".*?;",
                re.IGNORECASE)),
            # Enumerator hierarchy inside definitions
            ("clause",                  re.compile(r"^\d+[A-Z]?\.\d+[A-Z]?(?:\s|$)")),
            ("def_sub_clause",          re.compile(r"^\([A-Z]\)")),
            ("def_sub_sub_clause",      re.compile(r"^\((?!\))(?:x{0,3})(?:ix|iv|v?i{0,3})\)")),
            ("def_sub_sub_sub_clause",  re.compile(r"^\([a-z]{1,2}\)")),
            ("def_sub_sub_sub_sub_clause", re.compile(r"^\([0-9]+\)")),
        ]
        self.depth_definitions: Dict[str, int] = {
            "part": 0, "part_title": 1, "condition": 2, "definition": 3, "clause": 4,
            "def_sub_clause": 5, "def_sub_sub_clause": 6,
            "def_sub_sub_sub_clause": 7, "def_sub_sub_sub_sub_clause": 8,
        }

        self.unpushed_kinds = {"subtitle", "text"}
        
        self.junk_patterns = [
            re.compile(r"^DRAFT:", re.IGNORECASE),
            re.compile(r"^\d+$"),
            re.compile(r"Note to Reader:", re.IGNORECASE),
            re.compile(r"^\[.*\]$"),
            re.compile(r"^OFFICIAL\s*$", re.IGNORECASE),
        ]
        self.toc_line_regex = re.compile(r'^(.*?)\s*\.*\s*(\d+)?\s*$')
        self.part_regex = re.compile(r'^Part\s+(\d+\s*[A-Z]?)(?=\s|$)\s*(.*)$')
        self.condition_regex = re.compile(r'^(\d+[A-Z]?)\.(?:\s+(.*)|$)')
        self.annex_regex = re.compile(r'^(Annex|Appendix|Schedule)\s+(\d+[A-Z]?)\s*(.*)$', re.IGNORECASE)
        self.cond_num_regex = re.compile(r"^(\d+[A-Z]?)\.(?:\s|$)")
