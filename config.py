#!/usr/bin/env python3
"""
Configuration module for LCHA search system.
Loads environment variables from .env file.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration constants for LCHA search."""

    # Isaacus API
    ISAACUS_API_KEY = os.getenv("ISAACUS_API_KEY")
    ISAACUS_MODEL_ID = "kanon-2-embedder"

    # File paths
    SEARCH_DIR = "data/search"
    DATA_FILE = "lcha_structure_v4.json"

    # Search defaults
    DEFAULT_K = 5  # Number of results to return

    @classmethod
    def validate(cls):
        """Validate that required configuration is present."""
        if not cls.ISAACUS_API_KEY:
            raise ValueError(
                "ISAACUS_API_KEY not found! "
                "Please set it in .env file or environment variable."
            )
        return True
