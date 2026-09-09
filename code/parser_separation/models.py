from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class FlatTextSection(BaseModel):
    id: int
    text: str
    label: Optional[str] = None
    provenance: Optional[List[Dict[str, Any]]] = None
    absorbed: Optional[List[int]] = None
    document_id: Optional[str] = None

class TocNode(BaseModel):
    kind: str
    depth: int
    number: Optional[str] = None
    title: str
    page: Optional[int] = None
    line_id: Optional[int] = None
    provenance: Optional[List[Dict[str, Any]]] = None
    absorbed: Optional[List[int]] = None
    children: List['TocNode'] = Field(default_factory=list)
    
    # TASK-03 fields
    label_depth: Optional[int] = None
    series: Optional[str] = None
    
    # TASK-05 fields
    document_id: Optional[str] = None
    node_uid: Optional[str] = None
    parent_uid: Optional[str] = None
    
    # TASK-06 fields
    text_full: Optional[str] = None
    breadcrumb: Optional[str] = None
    text_sha256: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None

class DocumentMetadata(BaseModel):
    id: str
    title: str
    scheme: str
    round: str
    version: str
    source_file: str
    source_sha256: str
    page_count: int
    parsed_at: str
    parser_version: str
    config_profile: str

class DocumentOutput(BaseModel):
    document: DocumentMetadata
    main_body: TocNode
    annexes: Dict[int, FlatTextSection]
