from collections import defaultdict
import re
from typing import Dict, Any, List, Optional
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

    def clean_ocr_symbols(self, text: str) -> str:
        # Standardize Private Use Area font mapping glyphs
        text = text.replace('\uf06c', '•')
        text = text.replace('\uf0b7', '•')
        text = text.replace('\uf0b4', '*')
        text = text.replace('\uf02d', '-')
        text = text.replace('\uf03d', '=')
        text = text.replace('\uf02b', '+')
        text = text.replace('\uf02a', '*')
        text = text.replace('\uf02f', '/')
        text = text.replace('\uf028', '(')
        text = text.replace('\uf029', ')')
        
        # Scrambled math formula reconstructions
        text = text.replace('( ) t t t MRP SP MIN SP , Difference -=', 'Difference_t = MIN(SP_t, MRP_t) - MRP_t')
        text = text.replace('Difference_t = MIN(SP_t, MRP_t) - MRP_t', 'Difference_t = MIN(SP_t, MRP_t) - MRP_t')
        text = text.replace('Baseload  Difference  Amount t t t t TLM M CHPQM RQM h MAX MIN Q * * * * * =', 
                            'Baseload Difference Amount = Difference_t * MAX(MIN(Q_t, M_t) * h_t * RQM_t * CHPQM_t * (1 - TLM_t), 0)')
        text = text.replace('Intermittent Difference Amount = ( ) ( ) ,0 , Difference t t t t TLM M h MAX MIN Q * * *',
                            'Intermittent Difference Amount = Difference_t * MAX(MIN(Q_t, M_t) * h_t * (1 - TLM_t), 0)')
        text = text.replace('CHPQM RQM HID N TLM D ALF IC * * * * - * * * =', 
                            'Collateral Amount = IC * ALF * RQM * CHPQM * (1 - TLM_D) * HID * N')
        return text

    def split_definitions_text(self, full_text: str) -> List[str]:
        # Split on space that is preceded by a semicolon and followed by a definition pattern
        pattern = re.compile(
            r'(?<=;)\s+(?='
            r'(?:\'[^\n]{2,80}?\'|"[^\n]{2,80}?"|\u201c[^\n]{2,80}?\u201d|\u2018[^\n]{2,80}?\u2019)'
            r'\s*\d*[A-Z]?\s*'
            r'(?:means|has\s+the\s+meaning|shall\s+have|shall\s+mean|is\b|or\b)'
            r')',
            re.IGNORECASE
        )
        parts = pattern.split(full_text)
        return [p.strip() for p in parts if p.strip()]

    def classify(self, text: str, is_definition: bool = False) -> str:
        patterns = self.config.patterns_definitions if is_definition else self.config.patterns_main_body
        for kind, pattern in patterns:
            if pattern.match(text):
                return kind
        return "text"

    def flatten_text(self, doc_dict: Dict[str, Any]) -> List[FlatTextSection]:
        raw_sections = []
        skip_labels = {"page_header", "page_footer"}
        for item in doc_dict.get('texts', []):
            ref = item.get('self_ref', "")
            sid = ref.split('/')[-1]
            if not sid.isdigit():
                continue
            if item.get('label') in skip_labels:
                continue
            raw_text = item.get("text") or item.get("orig") or ""
            text = raw_text.strip()
            if any(junk.search(text) for junk in self.config.junk_patterns):
                continue
            
            # Clean OCR symbols in raw text
            text = self.clean_ocr_symbols(text)
            
            raw_sections.append(FlatTextSection(
                id=int(sid),
                text=text,
                label=item.get('label'),
                provenance=item.get('prov'),
            ))
        raw_sections.sort(key=lambda t: t.id)

        # Merge only split definition lines using look-ahead
        text_sections = []
        i = 0
        while i < len(raw_sections):
            item = raw_sections[i]
            
            # If this line is already a complete definition, keep it as is
            if DEF_REGEX.match(item.text) or SPLIT_DEF_REGEX.match(item.text):
                text_sections.append(FlatTextSection(
                    id=item.id,
                    text=item.text,
                    label="definition",
                    provenance=item.provenance
                ))
                i += 1
                continue
                
            # Check if this line starts a split definition
            if item.label in ("text", "list_item", "footnote"):
                merged = False
                for k in range(1, 4):
                    if i + k >= len(raw_sections):
                        break
                    if any(raw_sections[m].label not in ("text", "list_item", "footnote") for m in range(i + 1, i + k + 1)):
                        break
                        
                    candidate_text = " ".join(raw_sections[m].text for m in range(i, i + k + 1))
                    if DEF_REGEX.match(candidate_text) or SPLIT_DEF_REGEX.match(candidate_text):
                        is_def = DEF_REGEX.match(candidate_text) or SPLIT_DEF_REGEX.match(candidate_text)
                        
                        # Find the correct starting item inside the merged block
                        source_item = item
                        prefix = candidate_text[:40].strip()
                        m_match = DEF_REGEX.match(candidate_text) or SPLIT_DEF_REGEX.match(candidate_text)
                        if m_match:
                            # If it is a group match, extract it
                            prefix = candidate_text[:m_match.end()].strip()
                        for m in range(i, i + k + 1):
                            c = raw_sections[m]
                            if prefix in c.text or any(word in c.text for word in prefix.split()[:3] if len(word) > 2):
                                source_item = c
                                break
                                
                        combined_prov = []
                        for m in range(i, i + k + 1):
                            c = raw_sections[m]
                            if c.provenance:
                                combined_prov.extend(c.provenance)
                        
                        text_sections.append(FlatTextSection(
                            id=source_item.id,
                            text=candidate_text,
                            label="definition" if is_def else "text",
                            provenance=combined_prov if combined_prov else None,
                            absorbed=[raw_sections[m].id for m in range(i, i + k + 1) if raw_sections[m].id != source_item.id]
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
        
        # Stage 2: Merge fragmented sentences/paragraphs
        healed_sections = []
        i = 0
        while i < len(text_sections):
            item = text_sections[i]
            j = i + 1
            merged_text = item.text
            merged_items = [item]
            
            while j < len(text_sections) and self._should_merge(merged_items[-1], text_sections[j]):
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
                
        healed_sections.sort(key=lambda t: t.id)
        return healed_sections

    def _should_merge(self, line1: FlatTextSection, line2: FlatTextSection) -> bool:
        # Only merge standard text, list_item, or footnote labels
        if line1.label not in ("text", "list_item", "footnote") or line2.label not in ("text", "list_item", "footnote"):
            return False
        if line1.label == "definition" or line2.label == "definition":
            return False
        t1 = line1.text.strip()
        t2 = line2.text.strip()
        if not t1 or not t2:
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

    def build_toc_tree(self, doc_dict: Dict[str, Any], text_sections: List[FlatTextSection]) -> TocNode:
        id_by_number = {}
        for line in text_sections:
            m = self.config.cond_num_regex.match(line.text)
            if m:
                # Store the line id mapping for each condition number
                id_by_number.setdefault(int(m.group(1)), line.id)

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
                node = self._make_node("annex", f"{annex_type} {number}", title, page)
                tree.children.append(node)
                annex_nodes.append(node)
                current_part = node
                continue

            kind = self.classify(text)
            if kind == "part":
                number, title = self.config.part_regex.match(text).groups()
                current_part = self._make_node("part", number.replace(" ", ""), title, page)
                tree.children.append(current_part)
            elif kind == "condition":
                number, title = self.config.condition_regex.match(text).groups()
                title_str = title or ""
                # Clean dot leaders if the title contains them
                title_str = re.sub(r"^\.[\s\.]*", "", title_str).strip()
                cond_id = id_by_number.get(int(number))
                if not title_str and cond_id is not None:
                    # Find the line in text_sections
                    for line in text_sections:
                        if line.id == cond_id:
                            body_text = line.text
                            # Remove "78." prefix
                            body_text = re.sub(r"^\d+\.\s*", "", body_text).strip()
                            title_str = body_text
                            break
                node = self._make_node("condition", int(number), title_str, page, line_id=cond_id)
                if current_part:
                    current_part.children.append(node)
                else:
                    tree.children.append(node)

        # Sequentially map annex nodes to their line IDs in the flattened text
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
                            current_search_idx = idx + 1
                            break
        return tree

    def _make_node(self, kind: str, number: Any, title: str, page: Any, line_id: Optional[int] = None) -> TocNode:
        return TocNode(
            kind=kind,
            depth=self.config.depth_main_body[kind],
            number=number,
            title=title.strip(),
            page=page,
            line_id=line_id
        )
