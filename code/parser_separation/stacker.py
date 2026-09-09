import re
from typing import Dict, Any, List, Optional, Tuple
from .models import TocNode, FlatTextSection

# Map definition-internal kind names to standard output names
DEF_KIND_NORMALIZE = {
    "def_sub_clause": "sub_clause",
    "def_sub_sub_clause": "sub_sub_clause",
    "def_sub_sub_sub_clause": "sub_sub_sub_clause",
    "def_sub_sub_sub_sub_clause": "sub_sub_sub_sub_clause",
}

# Pattern to detect clause-numbered lines inside definitions (e.g. "1.2", "1.3(A)", "12A.1")
CLAUSE_NUM_RE = re.compile(r"^\d+[A-Z]?\.\d+[A-Z]?(?:\s|[A-Z0-9'\"\u201c\u2018(]|$)")

ROMAN_VALS = {
    'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6, 'vii': 7, 'viii': 8, 'ix': 9, 'x': 10,
    'xi': 11, 'xii': 12, 'xiii': 13, 'xiv': 14, 'xv': 15, 'xvi': 16, 'xvii': 17, 'xviii': 18, 'xix': 19, 'xx': 20,
    'xxi': 21, 'xxii': 22, 'xxiii': 23, 'xxiv': 24, 'xxv': 25, 'xxvi': 26, 'xxvii': 27, 'xxviii': 28, 'xxix': 29, 'xxx': 30,
    'xxxi': 31, 'xxxii': 32, 'xxxiii': 33, 'xxxiv': 34, 'xxxv': 35, 'xxxvi': 36, 'xxxvii': 37, 'xxxviii': 38, 'xxxix': 39,
    'xl': 40, 'xli': 41, 'xlii': 42, 'xliii': 43, 'xliv': 44, 'xlv': 45, 'xlvi': 46, 'xlvii': 47, 'xlviii': 48, 'xlix': 49,
    'l': 50, 'li': 51, 'lii': 52, 'liii': 53, 'liv': 54, 'lv': 55, 'lvi': 56, 'lvii': 57, 'lviii': 58, 'lix': 59
}

def extract_enum(text: str) -> Optional[str]:
    m = re.match(r"^\(([A-Za-z0-9]+)\)", text.strip())
    if m:
        return m.group(1)
    return None

def alpha_to_int(s: str) -> int:
    s = s.lower()
    if len(s) == 1:
        return ord(s) - ord('a') + 1
    elif len(s) == 2 and s[0] == s[1]:
        return 26 + ord(s[0]) - ord('a') + 1
    raise ValueError(f"Invalid alpha enumerator: {s}")

class Stacker:
    def __init__(self, processor):
        self.processor = processor
        self.config = processor.config

    def build_gaps(self, text_sections: List[FlatTextSection], matches: List[Dict[str, Any]], end_boundary: Optional[int] = None) -> Dict[int, Dict[int, str]]:
        flatten_id_numbers = [m["id"] for m in matches]
        text_by_id = {line.id: line.text for line in text_sections}
        
        gaps_by_id = {}
        if end_boundary is None:
            end_boundary = text_sections[-1].id + 1 if text_sections else 0
        boundaries = flatten_id_numbers + [end_boundary]
        
        for x, y in zip(boundaries, boundaries[1:]):
            gaps_by_id[x] = {gap_id: text_by_id.get(gap_id) for gap_id in range(x + 1, y)}
        return gaps_by_id

    def _resolve_lowercase_token(self, s: str, stack: List[Any], is_def: bool, is_cfd_2017: bool) -> Tuple[str, int]:
        s_lower = s.lower()
        
        # Check if we can continue an existing list in the stack
        for idx in range(len(stack) - 1, -1, -1):
            parent, parent_depth = stack[idx]
            if parent.children:
                last_child = parent.children[-1]
                last_enum = extract_enum(last_child.title)
                if last_enum:
                    last_enum_lower = last_enum.lower()
                    # Try Roman successor
                    if last_enum_lower in ROMAN_VALS and s_lower in ROMAN_VALS:
                        if ROMAN_VALS[s_lower] == ROMAN_VALS[last_enum_lower] + 1:
                            return last_child.kind, last_child.depth
                    # Try Alpha successor
                    try:
                        val_prev = alpha_to_int(last_enum_lower)
                        val_curr = alpha_to_int(s_lower)
                        if val_curr == val_prev + 1:
                            return last_child.kind, last_child.depth
                    except Exception:
                        pass

        # If it's a fresh list start, determine series
        if s_lower == 'a':
            series = 'lower_alpha'
        elif s_lower == 'i':
            series = 'lower_roman'
        else:
            if s_lower in ROMAN_VALS:
                series = 'lower_roman'
            else:
                series = 'lower_alpha'

        # Map series to kind & depth
        if is_def:
            if series == 'lower_roman':
                kind = 'def_sub_sub_clause'
            else:
                kind = 'def_sub_sub_sub_clause'
            depth = self.config.depth_definitions[kind]
        else:
            if series == 'lower_roman':
                if is_cfd_2017:
                    kind = 'sub_clause'
                else:
                    kind = 'sub_sub_clause'
            else:
                if is_cfd_2017:
                    kind = 'sub_sub_clause'
                else:
                    kind = 'sub_sub_sub_clause'
            depth = self.config.depth_main_body[kind]

        return kind, depth

    def stack_content(self, condition_node: TocNode, content_dict: Dict[int, str], text_sections: Optional[List[FlatTextSection]] = None):
        is_def = "DEFINITION" in condition_node.title.upper()
        patterns = self.config.patterns_definitions if is_def else self.config.patterns_main_body
        depths   = self.config.depth_definitions   if is_def else self.config.depth_main_body
        is_cfd_2017 = "FINAL_CFD_Standard_Terms_and_Conditions_V2" in self.config.name

        # Build a lookup for provenance and absorbed from flat text sections
        prov_by_id = {}
        absorbed_by_id = {}
        if text_sections is not None:
            for line in text_sections:
                if line.provenance:
                    prov_by_id[line.id] = line.provenance
                if line.absorbed:
                    absorbed_by_id[line.id] = line.absorbed

        stack = [(condition_node, condition_node.depth)]

        for line_id in sorted(content_dict):
            text = content_dict[line_id]
            if text is None or not text.strip():
                continue

            stripped = text.strip()

            is_dotted = False
            classified_kind = self.processor.classify(stripped, is_definition=is_def)
            if classified_kind == "clause":
                is_dotted = True
            elif is_def and CLAUSE_NUM_RE.match(stripped):
                is_dotted = True

            is_valid_clause = False
            if is_dotted:
                m_stem = re.match(r"^(\d+[A-Z]?)\.", stripped)
                if m_stem:
                    stem = m_stem.group(1).upper()
                    cond_stem = str(condition_node.number).strip().upper() if condition_node.number is not None else ""
                    if cond_stem:
                        base_stem = re.sub(r"[A-Z]+$", "", stem)
                        base_cond = re.sub(r"[A-Z]+$", "", cond_stem)
                        if stem == cond_stem or base_stem == base_cond:
                            is_valid_clause = True

            if is_valid_clause:
                kind = "clause"
                output_kind = "clause"
                depth = self.config.depth_definitions.get("clause", 4) if is_def else self.config.depth_main_body.get("clause", 4)
            else:
                kind = self.processor.classify(stripped, is_definition=is_def)
                if kind == "clause":
                    kind = "text"
                if kind in ("part", "condition"):
                    continue

                enum_val = extract_enum(stripped)
                if enum_val and re.match(r"^[a-z]{1,2}$", enum_val):
                    kind, depth = self._resolve_lowercase_token(enum_val, stack, is_def, is_cfd_2017)
                    output_kind = DEF_KIND_NORMALIZE.get(kind, kind)
                else:
                    output_kind = DEF_KIND_NORMALIZE.get(kind, kind)
                    depth = stack[-1][1] + 1 if kind in self.config.unpushed_kinds else depths[kind]

            node = TocNode(
                kind=output_kind,
                depth=depth,
                number="", 
                title=stripped,
                line_id=line_id,
                provenance=prov_by_id.get(line_id),
                absorbed=absorbed_by_id.get(line_id)
            )

            if output_kind == "clause":
                while len(stack) > 1 and stack[-1][0].kind not in ("condition", "part"):
                    stack.pop()
            else:
                while len(stack) > 1 and stack[-1][1] >= depth:
                    stack.pop()

            # R2.3: Hard invariant check
            if output_kind == "clause":
                for ancestor, _ in stack:
                    assert ancestor.kind != "definition", (
                        f"Invariant Violation: definition '{ancestor.title}' "
                        f"cannot have clause child/descendant '{stripped}' (line_id={line_id})"
                    )

            stack[-1][0].children.append(node)
            if kind not in self.config.unpushed_kinds:
                stack.append((node, depth))

    def _get_node_series(self, kind: str, title: str, is_cfd_2017: bool) -> str:
        title_stripped = title.strip()
        if kind in ("condition", "clause"):
            return "dotted"
        m = re.match(r"^\(([A-Za-z0-9]+)\)", title_stripped)
        if not m:
            return "none"
        enum = m.group(1)
        if enum.isdigit():
            return "numeric"
        if enum.isupper() and len(enum) == 1:
            return "upper_alpha"
        
        # Lowercase check
        if is_cfd_2017:
            if kind in ("sub_clause", "def_sub_sub_clause"):
                return "lower_roman"
            elif kind in ("sub_sub_clause", "def_sub_sub_sub_clause"):
                return "lower_alpha"
        else:
            if kind in ("sub_sub_clause", "def_sub_sub_clause"):
                return "lower_roman"
            elif kind in ("sub_sub_sub_clause", "def_sub_sub_sub_clause"):
                return "lower_alpha"
                
        if enum.lower() in ROMAN_VALS:
            return "lower_roman"
        return "lower_alpha"

    def _post_process_node(self, node: TocNode, parent: Optional[TocNode], document_id: str, is_cfd_2017: bool, breadcrumb_parts: List[str]):
        import hashlib
        
        # 1. Capture original depth as label_depth and set achieved depth
        node.label_depth = node.depth
        if parent is None:
            node.depth = -1
        else:
            node.depth = parent.depth + 1
            
        # 2. Get series
        node.series = self._get_node_series(node.kind, node.title, is_cfd_2017)
        
        # 3. TASK-05 fields: node_uid, parent_uid, document_id
        node.document_id = document_id
        if node.line_id is not None:
            node.node_uid = f"{document_id}:{node.line_id}"
        else:
            node.node_uid = f"{document_id}:{node.kind}:{node.number or ''}"
            
        if parent is not None:
            node.parent_uid = parent.node_uid
        else:
            node.parent_uid = None
            
        if node.number == "":
            node.number = None
            
        # 4. TASK-06 fields: Breadcrumb
        current_parts = list(breadcrumb_parts)
        part_str = None
        if node.kind == "part":
            part_str = f"Part {node.number}" if node.number else "Part"
        elif node.kind == "condition":
            part_str = f"Condition {node.number}" if node.number else "Condition"
        elif node.kind == "clause":
            m = re.match(r"^(\d+\.\d+)", node.title)
            if m:
                part_str = m.group(1)
            elif node.number:
                part_str = str(node.number)
            else:
                m_dots = re.match(r"^(\d+(?:\.\d+)+)", node.title)
                if m_dots:
                    part_str = m_dots.group(1)
        elif node.kind == "definition":
            m_def = re.match(r"^[\"'\u201c\u2018]\s*([^\"'\u201d\u2019\n]{2,80}?)\s*[\"'\u201d\u2019]", node.title.strip())
            if m_def:
                term = m_def.group(1).strip()
                part_str = f'"{term}"'
            else:
                part_str = "Definition"
        else:
            m = re.match(r"^(\([A-Za-z0-9]+\))", node.title.strip())
            if m:
                part_str = m.group(1)
                
        if part_str:
            current_parts.append(part_str)
            
        node.breadcrumb = " › ".join(current_parts) if current_parts else ""

        # Page range calculation
        pages = []
        if node.page is not None:
            pages.append(node.page)
        if node.provenance:
            for p in node.provenance:
                if p.get("page_no") is not None:
                    pages.append(p["page_no"])
                    
        # Recursively process children
        children_texts = []
        for child in node.children:
            self._post_process_node(child, node, document_id, is_cfd_2017, current_parts)
            if child.page_start is not None:
                pages.append(child.page_start)
            if child.page_end is not None:
                pages.append(child.page_end)
            children_texts.append(child.text_full)
            
        if pages:
            node.page_start = min(pages)
            node.page_end = max(pages)
        else:
            node.page_start = None
            node.page_end = None
            
        # text_full
        lines = [node.title] + children_texts
        node.text_full = "\n".join(lines)
        
        # text_sha256
        norm_text = " ".join(node.title.lower().split())
        node.text_sha256 = hashlib.sha256(norm_text.encode('utf-8')).hexdigest()
        
        # 5. R3.3: Collapse kind
        if node.kind != "root":
            if "sub_clause" in node.kind or "sub_sub_" in node.kind or "def_sub_" in node.kind:
                node.kind = "subclause"

    def post_process_tree(self, root_node: TocNode, document_id: str):
        is_cfd_2017 = "FINAL_CFD_Standard_Terms_and_Conditions_V2" in self.config.name
        self._post_process_node(root_node, None, document_id, is_cfd_2017, [])

