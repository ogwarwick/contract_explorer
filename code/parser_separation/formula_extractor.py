import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from PIL import Image

class FormulaExtractor:
    def __init__(self, crops_dir: Optional[Path] = None, cache_path: Optional[Path] = None):
        self.crops_dir = crops_dir or Path("contracts/formula_crops")
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path = cache_path or (self.crops_dir / "formula_latex_cache.json")
        self.cache: Dict[str, str] = self._load_cache()
        self._model = None

    def _load_cache(self) -> Dict[str, str]:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"  [FormulaExtractor] Warning loading cache: {e}")
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  [FormulaExtractor] Warning saving cache: {e}")

    def _get_model(self):
        if self._model is None:
            print("  [FormulaExtractor] Loading Pix2Tex (LatexOCR) model...")
            from pix2tex.cli import LatexOCR
            self._model = LatexOCR()
        return self._model

    def extract_formula_text(self, pdf_path: Optional[Path], doc_dict: Dict[str, Any], contract_slug: str) -> Dict[int, str]:
        """
        Extracts all formula items from doc_dict, crops their bounding boxes from pdf_path,
        runs Pix2Tex OCR, and returns a dict mapping line_id -> latex_string.
        """
        result_map: Dict[int, str] = {}
        formulas = []
        for item in doc_dict.get("texts", []):
            if item.get("label") == "formula":
                ref = item.get("self_ref", "")
                sid = ref.split("/")[-1]
                if sid.isdigit():
                    formulas.append((int(sid), item))

        if not formulas:
            return result_map

        doc = None
        if pdf_path and pdf_path.exists() and pdf_path.suffix.lower() == ".pdf":
            try:
                import fitz
                doc = fitz.open(pdf_path)
            except Exception as e:
                print(f"  [FormulaExtractor] Warning opening PDF {pdf_path}: {e}")

        contract_crops_dir = self.crops_dir / contract_slug
        contract_crops_dir.mkdir(parents=True, exist_ok=True)

        cached_hits = 0
        new_extractions = 0

        for line_id, item in formulas:
            prov_list = item.get("prov", [])
            orig_text = item.get("orig") or item.get("text") or ""

            if not prov_list or doc is None:
                result_map[line_id] = orig_text.strip()
                continue

            prov = prov_list[0]
            page_no = prov.get("page_no")
            bbox = prov.get("bbox")

            if page_no is None or not bbox or page_no < 1 or page_no > doc.page_count:
                result_map[line_id] = orig_text.strip()
                continue

            bbox_key = f"{contract_slug}_p{page_no}_line{line_id}"
            if bbox_key in self.cache:
                result_map[line_id] = self.cache[bbox_key]
                cached_hits += 1
                continue

            # Crop formula image from PDF page
            page = doc[page_no - 1]
            H = page.rect.height
            W = page.rect.width
            padding_x = 6
            padding_y = 4

            crop_rect = fitz.Rect(
                max(0, bbox["l"] - padding_x),
                max(0, H - bbox["t"] - padding_y),
                min(W, bbox["r"] + padding_x),
                min(H, H - bbox["b"] + padding_y)
            )

            crop_filename = f"page_{page_no}_line_{line_id}.png"
            crop_path = contract_crops_dir / crop_filename

            try:
                pix = page.get_pixmap(clip=crop_rect, dpi=200)
                pix.save(crop_path)
            except Exception as e:
                print(f"  [FormulaExtractor] Crop error on page {page_no}, line {line_id}: {e}")
                result_map[line_id] = orig_text.strip()
                continue

            # Run Pix2Tex OCR
            try:
                img = Image.open(crop_path)
                model = self._get_model()
                latex_str = model(img)
                latex_clean = latex_str.strip() if latex_str else orig_text.strip()
                self.cache[bbox_key] = latex_clean
                result_map[line_id] = latex_clean
                new_extractions += 1
            except Exception as e:
                print(f"  [FormulaExtractor] Pix2Tex OCR error on line {line_id}: {e}")
                result_map[line_id] = orig_text.strip()

        if doc:
            doc.close()

        self._save_cache()
        print(f"  [FormulaExtractor] Processed {len(formulas)} formulas for {contract_slug} (Cached: {cached_hits}, New OCR: {new_extractions})")
        return result_map
