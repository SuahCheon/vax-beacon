"""Knowledge DB loader for Vax-Beacon v4."""

import json
import os


def load_knowledge_db(base_path="knowledge"):
    """Load DDx and investigation protocol databases."""
    ddx_path = os.path.join(base_path, "ddx_myocarditis.json")
    protocols_path = os.path.join(base_path, "investigation_protocols.json")

    with open(ddx_path, encoding="utf-8") as f:
        ddx_db = json.load(f)
    with open(protocols_path, encoding="utf-8") as f:
        protocols_db = json.load(f)

    return {"ddx": ddx_db, "protocols": protocols_db}
