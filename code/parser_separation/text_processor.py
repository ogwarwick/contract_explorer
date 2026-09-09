from collections import defaultdict
import re
from typing import Dict, Any, List, Tuple, Optional
from .config import ParserConfig
from .models import TocNode, FlatTextSection

# Regex to match definitions (allowing internal quotes in term names)
DEF_REGEX = re.compile(
    r'^(?:"\s*([^\n]{2,80}?)\s*"'
    r'|\u201c\s*([^\n]{2,80}?)\s*\u201d'
    r"|'\s*([^\n]{2,80}?)\s*'"
    r'|\u2018\s*([^\n]{2,80}?)\s*\u2019)'
    r'\s*\d*[A-Z]?\s*'
    r'(?:means|has\s+the\s+meaning|shall\s+have|shall\s+mean|is\b|or\b'
    r'|Condition\b|paragraph\b|Annex\b|Schedule\b|Appendix\b|Part\b|formula\b|term\b)',
    re.IGNORECASE
)

# Regex to match split-quote glossary table rows
SPLIT_DEF_REGEX = re.compile(
    r"^['\"\u201c\u2018]\s*"
    r"[a-z0-9\s&-]{2,80}"  # Term name
    r"\s*['\"\u201d\u2019]?\s*"  # Optional closing quote
    r"(?:Condition|paragraph|Annex|Schedule|Appendix|Part|means|has\s+the\s+meaning|shall\s+have|shall\s+mean|is\b)"
    r".*?;",
    re.IGNORECASE
)

class TextProcessor:
    def __init__(self, config: ParserConfig):
        self.config = config
        import json
        from pathlib import Path
        exc_path = Path(__file__).resolve().parent / "expected_exceptions.json"
        if exc_path.exists():
            with open(exc_path, 'r', encoding='utf-8') as f:
                self.exceptions = json.load(f)
        else:
            self.exceptions = {}

    def clean_ocr_symbols(self, text: str) -> str:
        # Standardize quotes
        text = text.replace("“", '"').replace("”", '"')
        text = text.replace("‘", "'").replace("’", "'")
        text = text.replace("`", "'")
        # Standardize OCR dashes
        text = text.replace("–", "-").replace("—", "-").replace("\uf02d", "-")
        # Standardize Math / Symbol font characters from PDF exports
        symbol_map = {
            "\uf028": "(", "\uf029": ")", "\uf03d": "=",
            "\uf02b": "+", "\uf0b4": "×", "\uf0b7": "•",
            "\uf0e5": "∑", "\uf050": "P", "\uf0d5": "Π",
        }
        for k, v in symbol_map.items():
            text = text.replace(k, v)
        # Standardize spaces
        text = " ".join(text.split())
        return text

    def classify(self, text: str, is_definition: bool = False) -> str:
        patterns = self.config.patterns_definitions if is_definition else self.config.patterns_main_body
        for kind, pattern in patterns:
            if pattern.match(text):
                return kind
        return "text"

    def _extract_toc_lines(self, doc_dict: Dict[str, Any]) -> List[str]:
        lines = []
        for table in doc_dict.get('tables', []):
            if table.get('label') != 'document_index':
                continue
            rows = defaultdict(list)
            for cell in table['data']['table_cells']:
                rows[cell['start_row_offset_idx']].append(cell['text'])
            for idx in sorted(rows):
                lines.append(" ".join(rows[idx]).strip())
        return lines

    def _find_boundaries(self, doc_dict: Dict[str, Any], raw_sections: List[FlatTextSection]) -> Tuple[Optional[int], Optional[int]]:
        # 1. Find Condition 2 start ID
        cond_2_id = None
        for line in raw_sections:
            if line.label == "section_header" and re.match(r"^2\.(?:\s|$)", line.text):
                cond_2_id = line.id
                break
        if cond_2_id is None:
            for line in raw_sections:
                if re.match(r"^2\.1?\s+TERM", line.text, re.IGNORECASE):
                    cond_2_id = line.id
                    break

        # 2. Find First Annex ID from TOC
        first_annex_page = None
        toc_lines = self._extract_toc_lines(doc_dict)
        for toc_line in toc_lines:
            entry = self.config.toc_line_regex.match(toc_line)
            if entry:
                text = entry.group(1).strip()
                page = int(entry.group(2)) if entry.group(2) else None
                if self.config.annex_regex.match(text) and page:
                    first_annex_page = page
                    break
        
        first_annex_id = None
        if first_annex_page is not None:
            for line in raw_sections:
                if line.provenance:
                    page_no = line.provenance[0].get("page_no")
                    if page_no == first_annex_page:
                        first_annex_id = line.id
                        break
        
        return cond_2_id, first_annex_id

    def flatten_text(self, doc_dict: Dict[str, Any], formula_map: Optional[Dict[int, str]] = None) -> List[FlatTextSection]:
        raw_sections = []
        skip_labels = {"page_header", "page_footer"}
        structural_pat = re.compile(
            r"^(?:"
            r"\d+\.\d+(?:\s|$)"
            r"|(?:Condition\s+\d+|\d+\s+Condition)\b"
            r"|\([A-Za-z0-9]{1,5}\)(?:\s|$)"
            r")",
            re.IGNORECASE
        )
        rescued_lines = []

        for item in doc_dict.get('texts', []):
            ref = item.get('self_ref', "")
            sid = ref.split('/')[-1]
            if not sid.isdigit():
                continue
            
            line_id = int(sid)
            label = item.get('label')
            
            # Use LaTeX from formula_map if available for formulas
            if formula_map and line_id in formula_map:
                text = formula_map[line_id].strip()
            else:
                raw_text = item.get("text") or item.get("orig") or ""
                text = raw_text.strip()
            
            if label in skip_labels:
                if structural_pat.match(text):
                    rescued_lines.append(f"ID={sid} Label={label} Text={text!r}")
                else:
                    continue

            if any(junk.search(text) for junk in self.config.junk_patterns):
                continue
            
            text = self.clean_ocr_symbols(text)
            
            profile_name = self.config.name
            corrections = self.exceptions.get("layout_corrections", {}).get(profile_name, [])
            line_id = int(sid)
            for corr in corrections:
                if corr.get("line_id") == line_id:
                    pattern = corr.get("pattern")
                    replacement = corr.get("replacement")
                    prepend = corr.get("prepend")
                    if pattern in text:
                        text = text.replace(pattern, replacement)
                        if prepend:
                            text = prepend + " " + text
            
            raw_sections.append(FlatTextSection(
                id=line_id,
                text=text,
                label=item.get('label'),
                provenance=item.get('prov'),
            ))
        
        if rescued_lines:
            print(f"  [Rescue] Labeled structural headers/footers rescued in {self.config.name} ({len(rescued_lines)}):")
            for r in rescued_lines:
                print(f"    * {r}")

        raw_sections.sort(key=lambda t: t.id)

        # Segment the document
        cond_2_id, first_annex_id = self._find_boundaries(doc_dict, raw_sections)

        # Split into distinct segments
        defs_raw = []
        body_raw = []
        annex_raw = []

        for line in raw_sections:
            if cond_2_id is not None and line.id < cond_2_id:
                defs_raw.append(line)
            elif first_annex_id is not None and line.id >= first_annex_id:
                annex_raw.append(line)
            else:
                body_raw.append(line)

        # Process definitions segment first
        defs_processed = self._process_definitions(defs_raw)

        # Find the last actual definition in defs_processed
        last_def_idx = -1
        for idx in range(len(defs_processed) - 1, -1, -1):
            if defs_processed[idx].label == "definition":
                last_def_idx = idx
                break

        defs_final = defs_processed[:last_def_idx + 1]
        defs_residue = defs_processed[last_def_idx + 1:]

        # Process main body segment including the definitions residue
        body_processed = self._process_main_body(defs_residue + body_raw)
        annex_processed = self._process_annexes(annex_raw)

        # Stitch them back together
        all_sections = defs_final + body_processed + annex_processed
        all_sections.sort(key=lambda t: t.id)
        return all_sections

    def _process_definitions(self, defs_raw: List[FlatTextSection]) -> List[FlatTextSection]:
        # Stage 1: Look-Ahead Definition Merging
        text_sections = []
        i = 0
        while i < len(defs_raw):
            item = defs_raw[i]
            
            if DEF_REGEX.match(item.text) or SPLIT_DEF_REGEX.match(item.text):
                text_sections.append(FlatTextSection(
                    id=item.id,
                    text=item.text,
                    label="definition",
                    provenance=item.provenance
                ))
                i += 1
                continue
                
            if item.label in ("text", "list_item", "footnote"):
                merged = False
                for k in range(1, 4):
                    if i + k >= len(defs_raw):
                        break
                    if any(defs_raw[m].label not in ("text", "list_item", "footnote") for m in range(i + 1, i + k + 1)):
                        break
                        
                    candidate_text = " ".join(defs_raw[m].text for m in range(i, i + k + 1))
                    if DEF_REGEX.match(candidate_text) or SPLIT_DEF_REGEX.match(candidate_text):
                        is_def = DEF_REGEX.match(candidate_text) or SPLIT_DEF_REGEX.match(candidate_text)
                        
                        source_item = item
                        prefix = candidate_text[:40].strip()
                        m_match = DEF_REGEX.match(candidate_text) or SPLIT_DEF_REGEX.match(candidate_text)
                        if m_match:
                            prefix = candidate_text[:m_match.end()].strip()
                        for m in range(i, i + k + 1):
                            c = defs_raw[m]
                            if prefix in c.text or any(word in c.text for word in prefix.split()[:3] if len(word) > 2):
                                source_item = c
                                break
                                
                        combined_prov = []
                        for m in range(i, i + k + 1):
                            c = defs_raw[m]
                            if c.provenance:
                                combined_prov.extend(c.provenance)
                        
                        text_sections.append(FlatTextSection(
                            id=source_item.id,
                            text=candidate_text,
                            label="definition" if is_def else "text",
                            provenance=combined_prov if combined_prov else None,
                            absorbed=[defs_raw[m].id for m in range(i, i + k + 1) if defs_raw[m].id != source_item.id]
                        ))
                        i += k + 1
                        merged = True
                        break
                if not merged:
                    text_sections.append(item)
                    i += 1
            else:
                text_sections.append(item)
                i += 1

        text_sections.sort(key=lambda t: t.id)

        # Stage 2: Strictly protect list items/formulas inside definitions from merging
        healed_sections = []
        i = 0
        while i < len(text_sections):
            item = text_sections[i]
            j = i + 1
            merged_text = item.text
            merged_items = [item]
            
            # Definitions merge logic (only merge if it is NOT a limb and NOT a formula)
            while j < len(text_sections) and self._should_merge_defs(merged_items[-1], text_sections[j]):
                next_item = text_sections[j]
                if merged_text.endswith("-"):
                    merged_text = merged_text[:-1] + next_item.text
                else:
                    merged_text += " " + next_item.text
                merged_items.append(next_item)
                j += 1
                
            if len(merged_items) > 1:
                source_item = item
                absorbed_ids = []
                for mi in merged_items:
                    if mi.id != source_item.id:
                        absorbed_ids.append(mi.id)
                    if mi.absorbed:
                        absorbed_ids.extend(mi.absorbed)
                
                combined_prov = []
                for mi in merged_items:
                    if mi.provenance:
                        combined_prov.extend(mi.provenance)
                
                healed_sections.append(FlatTextSection(
                    id=source_item.id,
                    text=merged_text.strip(),
                    label=source_item.label,
                    provenance=combined_prov if combined_prov else None,
                    absorbed=absorbed_ids if absorbed_ids else None
                ))
                i = j
            else:
                healed_sections.append(item)
                i += 1
                
        return healed_sections

    def _is_structural_header(self, text: str) -> bool:
        t = text.strip()
        if re.match(r"^Part\s+\d+", t, re.IGNORECASE):
            return True
        if re.compile(r"^\d+\.(?:\s|$)").match(t):
            return True
        if re.compile(r"^\([A-Za-z0-9]{1,5}\)(?:\s|$)").match(t):
            return True
        if DEF_REGEX.match(t) or SPLIT_DEF_REGEX.match(t):
            return True
        return False

    def _should_merge_defs(self, line1: FlatTextSection, line2: FlatTextSection) -> bool:
        if line1.label not in ("text", "list_item", "footnote") or line2.label not in ("text", "list_item", "footnote"):
            return False
        if line1.label == "definition" or line2.label == "definition":
            return False
        
        t1 = line1.text.strip()
        t2 = line2.text.strip()
        if not t1 or not t2:
            return True
            
        # Protect Condition 1 clauses in definitions
        if re.match(r"^1\.\d+(?:\s|$)", t2):
            return False

        # Protect structural boundaries
        if self._is_structural_header(t2):
            return False

        # Merge formula stems with subsequent formulas
        t1_lower = t1.lower()
        if t1_lower.endswith("is:") or t1_lower.endswith("as:") or t1_lower.endswith("formula:"):
            if "=" in t2 or "+" in t2 or "/" in t2 or "*" in t2:
                return True
            
        # Do NOT merge if the next line starts with a list limb
        limb_pattern = re.compile(r"^\([A-Za-z0-9ivxIVX]+\)\s")
        if limb_pattern.match(t2):
            return False
            
        # Do NOT merge mathematical formulas
        formula_pattern = re.compile(r"^Eproducts\b|^\w+\s*=\s*\w+")
        if formula_pattern.match(t2):
            return False

        # Otherwise, follow standard termination checks
        sentence_terminators = {".", ";", ":"}
        ends_terminated = len(t1) > 0 and t1[-1] in sentence_terminators
        starts_lowercase = len(t2) > 0 and t2[0].islower()
        starts_punct = len(t2) > 0 and t2[0] in {"(", ")", ",", "=", "+", "-", "*", "/"}
        is_short = len(t1) < 20 or len(t2) < 20
        
        incomplete_endings = {"the", "and", "or", "of", "with", "for", "to", "in", "on", "at", "by", "a", "an", "is", "are"}
        t1_words = t1.lower().split()
        ends_incomplete = len(t1_words) > 0 and t1_words[-1].strip(".,;:()'") in incomplete_endings

        if not ends_terminated or starts_lowercase or starts_punct or is_short or ends_incomplete:
            return True
        return False

    def _process_main_body(self, body_raw: List[FlatTextSection]) -> List[FlatTextSection]:
        # Stage 1: Clean pass
        text_sections = list(body_raw)
        
        # Stage 2: Standard Fragment Healing
        healed_sections = []
        i = 0
        active_cond_num = 1
        while i < len(text_sections):
            item = text_sections[i]
            
            # Track current condition number stem
            cond_match = re.match(r"^(\d+)\.(?:\s|$)", item.text.strip())
            if cond_match:
                active_cond_num = int(cond_match.group(1))
                
            j = i + 1
            merged_text = item.text
            merged_items = [item]
            
            while j < len(text_sections) and self._should_merge_body(merged_items[-1], text_sections[j], active_cond_num):
                next_item = text_sections[j]
                if merged_text.endswith("-"):
                    merged_text = merged_text[:-1] + next_item.text
                else:
                    merged_text += " " + next_item.text
                merged_items.append(next_item)
                j += 1
                
            if len(merged_items) > 1:
                source_item = item
                absorbed_ids = []
                for mi in merged_items:
                    if mi.id != source_item.id:
                        absorbed_ids.append(mi.id)
                    if mi.absorbed:
                        absorbed_ids.extend(mi.absorbed)
                
                combined_prov = []
                for mi in merged_items:
                    if mi.provenance:
                        combined_prov.extend(mi.provenance)
                
                healed_sections.append(FlatTextSection(
                    id=source_item.id,
                    text=merged_text.strip(),
                    label=source_item.label,
                    provenance=combined_prov if combined_prov else None,
                    absorbed=absorbed_ids if absorbed_ids else None
                ))
                i = j
            else:
                healed_sections.append(item)
                i += 1
                
        return healed_sections

    def _should_merge_body(self, line1: FlatTextSection, line2: FlatTextSection, active_cond_num: Optional[Any] = None) -> bool:
        if line1.label not in ("text", "list_item", "footnote", "formula") or line2.label not in ("text", "list_item", "footnote", "formula"):
            return False
        
        t1 = line1.text.strip()
        t2 = line2.text.strip()
        if not t1 or not t2:
            return True

        # Protect clause structural boundaries (must match the active condition stem)
        m_dots = re.match(r"^(\d+[A-Z]?)\.(\d+[A-Z]?)(?:\s|$)", t2)
        if m_dots:
            stem = m_dots.group(1).upper()
            if active_cond_num is not None and stem == str(active_cond_num).upper():
                return False

        # Protect structural boundaries
        if self._is_structural_header(t2):
            return False

        # Merge formula stems with subsequent formulas
        t1_lower = t1.lower()
        if t1_lower.endswith("is:") or t1_lower.endswith("as:") or t1_lower.endswith("formula:"):
            if "=" in t2 or "+" in t2 or "/" in t2 or "*" in t2:
                return True
        
        limb_pattern = re.compile(r"^\([A-Za-z0-9ivxIVX]+\)\s")
        is_limb1 = bool(limb_pattern.match(t1))
        is_limb2 = bool(limb_pattern.match(t2))
        
        incomplete_endings = {"the", "and", "or", "of", "with", "for", "to", "in", "on", "at", "by", "a", "an", "is", "are"}
        t1_words = t1.lower().split()
        ends_incomplete = len(t1_words) > 0 and t1_words[-1].strip(".,;:()'") in incomplete_endings
        
        if is_limb2 and not ends_incomplete:
            return False
            
        sentence_terminators = {".", ";", ":"}
        ends_terminated = len(t1) > 0 and t1[-1] in sentence_terminators
        starts_lowercase = len(t2) > 0 and t2[0].islower()
        starts_punct = len(t2) > 0 and t2[0] in {"(", ")", ",", "=", "+", "-", "*", "/"}
        is_short = len(t1) < 20 or len(t2) < 20
        
        if not ends_terminated or starts_lowercase or starts_punct or is_short or ends_incomplete:
            return True
        return False

    def _process_annexes(self, annex_raw: List[FlatTextSection]) -> List[FlatTextSection]:
        # Minimal merging to prevent template/signature fields collapse
        text_sections = list(annex_raw)
        healed_sections = []
        i = 0
        while i < len(text_sections):
            item = text_sections[i]
            j = i + 1
            merged_text = item.text
            merged_items = [item]
            
            while j < len(text_sections) and self._should_merge_annex(merged_items[-1], text_sections[j]):
                next_item = text_sections[j]
                if merged_text.endswith("-"):
                    merged_text = merged_text[:-1] + next_item.text
                else:
                    merged_text += " " + next_item.text
                merged_items.append(next_item)
                j += 1
                
            if len(merged_items) > 1:
                source_item = item
                absorbed_ids = []
                for mi in merged_items:
                    if mi.id != source_item.id:
                        absorbed_ids.append(mi.id)
                    if mi.absorbed:
                        absorbed_ids.extend(mi.absorbed)
                
                combined_prov = []
                for mi in merged_items:
                    if mi.provenance:
                        combined_prov.extend(mi.provenance)
                
                healed_sections.append(FlatTextSection(
                    id=source_item.id,
                    text=merged_text.strip(),
                    label=source_item.label,
                    provenance=combined_prov if combined_prov else None,
                    absorbed=absorbed_ids if absorbed_ids else None
                ))
                i = j
            else:
                healed_sections.append(item)
                i += 1
                
        return healed_sections

    def _should_merge_annex(self, line1: FlatTextSection, line2: FlatTextSection) -> bool:
        if line1.label not in ("text", "list_item", "footnote") or line2.label not in ("text", "list_item", "footnote"):
            return False
        
        t1 = line1.text.strip()
        t2 = line2.text.strip()
        if not t1 or not t2:
            return True

        # Protect annex clause boundaries
        if re.match(r"^\d+\.\d+(?:\s|$)", t2):
            return False

        # Protect structural boundaries
        if self._is_structural_header(t2):
            return False
        
        # Do not merge if either is a line representation or form label (like "Name: ______" or "Signed: ______")
        signature_fields = {"signature", "signed", "name", "title", "date", "address", "attention"}
        t1_lower = t1.lower()
        t2_lower = t2.lower()
        if any(f in t1_lower for f in signature_fields) or any(f in t2_lower for f in signature_fields):
            return False
            
        limb_pattern = re.compile(r"^\([A-Za-z0-9ivxIVX]+\)\s")
        is_limb1 = bool(limb_pattern.match(t1))
        is_limb2 = bool(limb_pattern.match(t2))
        
        incomplete_endings = {"the", "and", "or", "of", "with", "for", "to", "in", "on", "at", "by", "a", "an", "is", "are"}
        t1_words = t1.lower().split()
        ends_incomplete = len(t1_words) > 0 and t1_words[-1].strip(".,;:()'") in incomplete_endings
        
        if is_limb2 and not ends_incomplete:
            return False
            
        sentence_terminators = {".", ";", ":"}
        ends_terminated = len(t1) > 0 and t1[-1] in sentence_terminators
        starts_lowercase = len(t2) > 0 and t2[0].islower()
        starts_punct = len(t2) > 0 and t2[0] in {"(", ")", ",", "=", "+", "-", "*", "/"}
        is_short = len(t1) < 20 or len(t2) < 20
        
        if not ends_terminated or starts_lowercase or starts_punct or is_short or ends_incomplete:
            return True
        return False

    def build_toc_tree(self, doc_dict: Dict[str, Any], text_sections: List[FlatTextSection]) -> TocNode:
        id_by_number = {}
        for line in text_sections:
            m = self.config.cond_num_regex.match(line.text)
            if m:
                id_by_number.setdefault(str(m.group(1)).strip().upper(), line.id)

        tree = TocNode(
            kind="root",
            depth=-1,
            number="",
            title="Root Table of Contents",
            page=None,
            line_id=None
        )
        current_part = None
        annex_nodes = []

        for toc_line in self._extract_toc_lines(doc_dict):
            if any(junk.search(toc_line) for junk in self.config.junk_patterns):
                continue
            entry = self.config.toc_line_regex.match(toc_line)
            if not entry:
                continue
            
            text = entry.group(1).strip()
            page = int(entry.group(2)) if entry.group(2) else None

            annex_match = self.config.annex_regex.match(text)
            if annex_match:
                annex_type, number, title = annex_match.groups()
                node = self._make_node("annex", f"{annex_type} {number}", title, page, text_sections=text_sections)
                tree.children.append(node)
                annex_nodes.append(node)
                current_part = node
                continue

            kind = self.classify(text)
            if kind == "part":
                number, title = self.config.part_regex.match(text).groups()
                current_part = self._make_node("part", number.replace(" ", ""), title, page, text_sections=text_sections)
                tree.children.append(current_part)
            elif kind == "condition":
                number, title = self.config.condition_regex.match(text).groups()
                title_str = title or ""
                title_str = re.sub(r"^\.[\s\.]*", "", title_str).strip()
                cond_id = id_by_number.get(str(number).strip().upper())
                if not title_str and cond_id is not None:
                    for line in text_sections:
                        if line.id == cond_id:
                            body_text = line.text
                            body_text = re.sub(r"^\d+[A-Z]?\.\s*", "", body_text).strip()
                            title_str = body_text
                            break
                node = self._make_node("condition", str(number).strip(), title_str, page, line_id=cond_id, text_sections=text_sections)
                if current_part:
                    current_part.children.append(node)
                else:
                    tree.children.append(node)

        # Map annexes
        last_cond_id = None
        for child in tree.children:
            if child.kind == "part":
                for cond in child.children:
                    if cond.kind == "condition" and cond.line_id is not None:
                        last_cond_id = cond.line_id

        current_search_idx = 0
        if last_cond_id is not None:
            for idx, line in enumerate(text_sections):
                if line.id == last_cond_id:
                    current_search_idx = idx
                    break

        for node in annex_nodes:
            parts = node.number.split()
            if len(parts) >= 2:
                atype = parts[0].lower()
                num_str = parts[1]
                
                for idx in range(current_search_idx, len(text_sections)):
                    line = text_sections[idx]
                    am = self.config.annex_regex.match(line.text.strip())
                    if am:
                        line_atype, line_num_str, _ = am.groups()
                        if line_atype.lower() == atype and line_num_str.strip() == num_str:
                            node.line_id = line.id
                            node.provenance = line.provenance
                            node.absorbed = line.absorbed
                            current_search_idx = idx + 1
                            break
        return tree

    def _make_node(self, kind: str, number: Any, title: str, page: Any, line_id: Optional[int] = None, text_sections: Optional[List[FlatTextSection]] = None) -> TocNode:
        prov = None
        absorbed = None
        if line_id is not None and text_sections is not None:
            for line in text_sections:
                if line.id == line_id:
                    prov = line.provenance
                    absorbed = line.absorbed
                    break
        num_val = None
        if number is not None and number != "":
            num_val = str(number)
        return TocNode(
            kind=kind,
            depth=self.config.depth_main_body[kind],
            number=num_val,
            title=title.strip(),
            page=page,
            line_id=line_id,
            provenance=prov,
            absorbed=absorbed
        )
