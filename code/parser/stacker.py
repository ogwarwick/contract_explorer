from typing import Dict, Any, List, Optional
from .models import TocNode, FlatTextSection

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

    def stack_content(self, condition_node: TocNode, content_dict: Dict[int, str]):
        is_def = "DEFINITION" in condition_node.title.upper()
        patterns = self.config.patterns_definitions if is_def else self.config.patterns_main_body
        depths   = self.config.depth_definitions   if is_def else self.config.depth_main_body

        stack = [(condition_node, condition_node.depth)]

        for line_id in sorted(content_dict):
            text = content_dict[line_id]
            if text is None or not text.strip():
                continue

            kind = self.processor.classify(text.strip(), is_definition=is_def)
            if kind in ("part", "condition"):
                continue

            depth = stack[-1][1] + 1 if kind in self.config.unpushed_kinds else depths[kind]
            node = TocNode(
                kind=kind,
                depth=depth,
                number="", 
                title=text.strip(),
                line_id=line_id
            )

            while len(stack) > 1 and stack[-1][1] >= depth:
                stack.pop()
            stack[-1][0].children.append(node)
            if kind not in self.config.unpushed_kinds:
                stack.append((node, depth))
