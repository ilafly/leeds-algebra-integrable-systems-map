from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .core import ROOT, dump_json, load_config
from .http import CachedHTTP
from .pipeline import analyse, collect
from .report import write_reports
from .store import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reproducible Leeds mathematical research map")
    parser.add_argument("command", choices=["collect", "analyse", "report", "export-reviews", "import-reviews"])
    parser.add_argument("--config", type=Path, default=ROOT / "config/researchers.toml")
    parser.add_argument("--database", type=Path, default=ROOT / "data/map.sqlite")
    parser.add_argument("--file", type=Path, default=ROOT / "data/reviews.json")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch successful responses, retaining an explicit stale-cache fallback")
    parser.add_argument("--offline", action="store_true", help="Use only the local HTTP cache")
    parser.add_argument("--skip-enrichment", action="store_true", help="Skip supplementary Crossref/arXiv requests")
    parser.add_argument("--limit", type=int, help="Override publications per researcher")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    store = Store(args.database)
    if args.command == "export-reviews":
        dump_json(args.file, store.reviews())
        print(f"Reviews exported to {args.file}")
        return 0
    if args.command == "import-reviews":
        store.import_reviews(json.loads(args.file.read_text(encoding="utf-8")))
        print("Review decisions imported")
        return 0
    snapshot = store.load()
    if args.command == "collect":
        cfg = load_config(args.config)
        if args.limit is not None:
            if args.limit <= 0:
                parser.error("--limit must be positive")
            cfg["collection"]["max_publications"] = args.limit
        c = cfg["collection"]
        http = CachedHTTP(store, c.get("cache_days", 30), c.get("timeout_seconds", 25), args.refresh,
                          args.offline, c.get("contact_email", ""))
        snapshot = collect(cfg, http, args.skip_enrichment)
        if not snapshot["publications"]:
            dump_json(args.database.parent / "collection_attempt.json", snapshot)
            print("No publications collected. Previous snapshot preserved. See data/collection_attempt.json.", file=sys.stderr)
            return 1
    elif not snapshot:
        parser.error("No dataset yet. Run collect first.")
    elif args.command == "analyse":
        snapshot = analyse(snapshot["researchers"], snapshot["publications"], snapshot.get("collection"))
    if args.command in {"collect", "analyse"}:
        store.save(snapshot)
        dump_json(args.database.parent / "snapshot.json", snapshot)
    write_reports(snapshot, store.reviews(), args.database.parent.parent / "reports")
    included = sum(not p.get("quarantined") and not p.get("is_retracted") for p in snapshot["publications"])
    print(f"{len(snapshot['publications'])} retrieved publication records, {included} included in discovery; {len(snapshot['concepts'])} concepts; "
          f"{len(snapshot['connections'])} candidate researcher pairs. Reports written to reports/.")
    if any(r.get("status") != "verified" for r in snapshot["researchers"]):
        print("Some identities require review; no publications were collected for those identities.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
