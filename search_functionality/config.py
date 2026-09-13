import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables from .env file in workspace root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

class Config:
    ISAACUS_API_KEY = os.getenv("ISAACUS_API_KEY")
    ISAACUS_MODEL_ID = "kanon-2-embedder"
    DATABASE_URL = os.getenv("DATABASE_URL", "dbname=lcha")
    SEARCH_DIR = str(Path(__file__).resolve().parent / "data" / "search")
    DATA_FILE = str(Path(__file__).resolve().parent.parent / "contracts" / "parsed_outputs" / "parser_separation" / "low-carbon-hydrogen-agreement-standard-terms-and-conditions_stacked.json")

    @classmethod
    def validate(cls):
        if not cls.ISAACUS_API_KEY:
            raise ValueError("ISAACUS_API_KEY is not set in environment or .env file.")
