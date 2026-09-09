import json
import re
from pathlib import Path

cache_dir = Path("/Users/owenwarwick/lcha/contracts/docling_files")
files = [
    ("ar3_docling_export.json", "AR3"),
    ("ar4_docling_export.json", "AR4"),
    ("ar5_docling_export.json", "AR5"),
    ("ar6_docling_export.json", "AR6"),
    ("ar7_docling_export.json", "AR7"),
    ("icc_docling_export.json", "CCUS-ICC"),
    ("ccus-dpa-standard-terms-and-conditions-november-2022_docling_export.json", "CCUS-DPA"),
    ("FINAL_CFD_Standard_Terms_and_Conditions_V2-_13_March_2017__docling_export.json", "CfD-2017"),
    ("Generic_CfD_TCs__29_August_2014__docling_export.json", "CfD-2014"),
    ("lcha_docling_export.json", "LCHA")
]

patterns = [
    ("dotted_clause", re.compile(r"^\d+\.\d+(?:\s|$)")),
    ("leading_condition", re.compile(r"^(?:Condition\s+\d+|\d+\s+Condition)\b", re.IGNORECASE)),
    ("bracketed_enum", re.compile(r"^\([A-Za-z0-9]{1,5}\)(?:\s|$)"))
]

for filename, doc_name in files:
    path = cache_dir / filename
    if not path.exists():
        continue
    with open(path) as f:
        data = json.load(f)
    
    found = []
    for idx, item in enumerate(data.get("texts", [])):
        label = item.get("label")
        if label in ("page_header", "page_footer"):
            text = item.get("text", "").strip()
            for p_name, pat in patterns:
                if pat.match(text):
                    found.append((idx, label, p_name, text))
                    
    if found:
        print(f"=== {doc_name} matched structural headers/footers ({len(found)}) ===")
        for idx, label, p_name, text in found:
            print(f"  ID={idx} label={label} pat={p_name} text={text!r}")
