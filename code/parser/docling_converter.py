from pathlib import Path
import json
from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from docling.document_converter import PdfFormatOption

class DoclingConverter:
    def __init__(self, docling_cache_dir: Path):
        self.cache_dir = docling_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure pipeline options (OCR disabled for speed)
        opts = PdfPipelineOptions()
        opts.do_ocr = False
        opts.do_formula_enrichment = False
        
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )

    def _find_cached_path(self, pdf_path: Path) -> Path:
        name_lower = pdf_path.name.lower()
        
        # Try direct matching first
        direct_match = self.cache_dir / f"{pdf_path.stem}_docling_export.json"
        if direct_match.exists():
            return direct_match
            
        # Keyword-based mapping to existing cache files
        if "icc" in name_lower:
            match = self.cache_dir / "icc_docling_export.json"
            if match.exists():
                return match
        if "lcha" in name_lower or "hydrogen" in name_lower:
            match = self.cache_dir / "lcha_docling_export.json"
            if match.exists():
                return match
                
        # AR versions matching (e.g. ar3, ar-3, ar_3)
        for ar_num in ["ar1", "ar3", "ar4", "ar5", "ar6", "ar7"]:
            num_val = ar_num[2:]
            if ar_num in name_lower or f"ar-{num_val}" in name_lower or f"ar_{num_val}" in name_lower:
                match = self.cache_dir / f"{ar_num}_docling_export.json"
                if match.exists():
                    return match
                    
        return direct_match

    def convert_pdf(self, pdf_path: Path) -> Path:
        output_json_path = self._find_cached_path(pdf_path)
        
        # Check cache
        if output_json_path.exists():
            print(f"  [Cache Hit] {pdf_path.name} maps to existing cache: {output_json_path.name}")
            return output_json_path
            
        print(f"  [Cache Miss] Converting {pdf_path.name} to Docling JSON...")
        result = self.converter.convert(pdf_path)
        doc_dict = result.document.export_to_dict()
        
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(doc_dict, f, indent=2)
            
        print(f"  [Completed] Saved Docling export to {output_json_path.name}")
        return output_json_path
