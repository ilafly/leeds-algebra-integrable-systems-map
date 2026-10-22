from __future__ import annotations

import hashlib
import json
import re
import tomllib
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def stable_id(prefix, *parts):
    return prefix + ":" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def doi_key(value):
    value = unquote(value or "").strip().lower()
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value)
    return value if re.match(r"^10\.\d{4,9}/\S+$", value) else None


def arxiv_key(value):
    doi = doi_key(value)
    if doi and doi.startswith("10.48550/arxiv."):
        value = doi.removeprefix("10.48550/arxiv.")
    value = re.sub(r"^arxiv:\s*", "", value or "", flags=re.I)
    value = re.sub(r"^.*arxiv\.org/(?:abs|pdf)/", "", value or "")
    value = re.sub(r"(?:v\d+)?(?:\.pdf)?$", "", value)
    return value if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})", value) else None


def load_config(path=None):
    with open(path or ROOT / "config/researchers.toml", "rb") as f:
        cfg = tomllib.load(f)
    ids = [r["id"] for r in cfg["researchers"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Researcher IDs must be unique")
    if not cfg["collection"].get("max_publications", 40) > 0:
        raise ValueError("max_publications must be positive")
    return cfg


def dump_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def evidence(source, method, text, confidence, **extra):
    return {"source": source, "method": method, "evidence": text,
            "confidence": confidence, "review_status": "unreviewed", **extra}
