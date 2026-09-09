from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict, Union

class FlatTextSection(BaseModel):
    id: int
    text: str
    label: Optional[str] = None
    provenance: Optional[List[Dict[str, Any]]] = None
    absorbed: Optional[List[int]] = None

class TocNode(BaseModel):
    kind: str
    depth: int
    number: Union[str, int]
    title: str
    page: Optional[int] = None
    line_id: Optional[int] = None
    children: List['TocNode'] = Field(default_factory=list)

class DocumentOutput(BaseModel):
    main_body: TocNode
    annexes: Dict[int, FlatTextSection]
