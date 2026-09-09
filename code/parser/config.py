import re
from typing import Dict, List, Tuple

class ParserConfig:
    def __init__(self, name: str):
        self.name = name
        
        # Main Body Patterns
        self.patterns_main_body: List[Tuple[str, re.Pattern]] = [
            ("part",                    re.compile(r"^Part\s+\d+[A-Z]?\b")),
            ("condition",               re.compile(r"^\d+\.(?:\s|$)")),
            ("clause",                  re.compile(r"^\d+\.\d+(?:\s+[A-Z0-9'\"\u201c\u2018]|\s*$)")),
            ("sub_clause",              re.compile(r"^\([A-Z]\)")),
            ("sub_sub_clause",          re.compile(r"^\((?=[ivxlcdm]+\))[ivxlcdm]+\)")),
            ("sub_sub_sub_clause",      re.compile(r"^\([a-z]\)")),
            ("sub_sub_sub_sub_clause",  re.compile(r"^\([0-9]+\)")),
            ("subtitle",                re.compile(r"^[A-Z][A-Z0-9 &,\-]{8,60}$")),
        ]
        
        self.depth_main_body: Dict[str, int] = {
            "part": 0, "part_title": 1, "condition": 2, "condition_subtitle": 3,
            "clause": 4, "sub_clause": 5, "sub_sub_clause": 6, "sub_sub_sub_clause": 7, "sub_sub_sub_sub_clause": 8, "annex": 0,
        }

        # Definition Patterns
        self.patterns_definitions: List[Tuple[str, re.Pattern]] = [
            ("part",      re.compile(r"^Part\s+\d+[A-Z]?\b")),
            ("condition", re.compile(r"^\d+\.(?:\s|$)")),
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
        ]
        self.depth_definitions: Dict[str, int] = {
            "part": 0, "part_title": 1, "condition": 2, "definition": 3
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
        self.condition_regex = re.compile(r'^(\d+)\.(?:\s+(.*)|$)')
        self.annex_regex = re.compile(r'^(Annex|Appendix|Schedule)\s+(\d+)\s*(.*)$', re.IGNORECASE)
        self.cond_num_regex = re.compile(r"^(\d+)\.(?:\s|$)")
