from __future__ import annotations

import json
import math
import re
from collections import Counter
from itertools import combinations

from .core import ROOT, evidence, normalise, stable_id

STOP = set("a an the and or of to in on for by with from as at is are be we our this that these those it its into using via under over about between within without some any all not new study approach general based result results paper show prove give consider introduce obtain which can also has have such both two one finite dimensional mathematics mathematical model models structure structures theory properties examples class classes number associated their they then than".split())
HEADS = {"algebra", "algebras", "group", "groups", "groupoid", "groupoids", "braces", "bracoids", "equation", "equations", "invariants", "categories", "modules", "trusses", "semitrusses", "quandles", "biquandles", "biracks", "representations", "homology", "cohomology", "holonomy"}


def load_vocabulary(path=None):
    return json.loads((path or ROOT / "config/vocabulary.json").read_text(encoding="utf-8"))


def source_for(publication, field):
    for record in reversed(publication.get("provenance", [])):
        if field in record.get("fields", []):
            return record["source"]
    return publication["url"]


def excerpt(text, phrase):
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        if " " + phrase + " " in " " + normalise(sentence) + " ":
            tokens = [(normalise(m.group()), m.start()) for m in re.finditer(r"[^\W_]+", sentence)]
            words = phrase.split()
            for i in range(len(tokens) - len(words) + 1):
                if [t[0] for t in tokens[i:i + len(words)]] == words:
                    start = max(0, tokens[i][1] - 110)
                    return ("…" if start else "") + sentence[start:start + 420] + ("…" if len(sentence) > start + 420 else "")
            return sentence[:420]
    return text[:420]


def discover_phrases(documents, vocabulary):
    """Conservative recurring title phrases with a mathematical noun head."""
    aliases = {normalise(a) for label, values in vocabulary.items() for a in [label, *values]}
    counts = Counter()
    for text in documents:
        tokens = normalise(text).split()
        found = set()
        for size in (2, 3, 4):
            for i in range(len(tokens) - size + 1):
                words = tokens[i:i + size]
                if words[-1] not in HEADS or words[0] in STOP:
                    continue
                if any(w in STOP or w.isdigit() for w in words[:-1]):
                    continue
                plural = {"algebra": "algebras", "group": "groups", "groupoid": "groupoids",
                          "equation": "equations", "module": "modules"}
                words[-1] = plural.get(words[-1], words[-1])
                phrase = " ".join(words)
                # Exclude fragments of established vocabulary phrases, e.g. 'Baxter equation'.
                variants = {phrase, " ".join(tokens[i:i + size])}
                fragment = any(" " + v + " " in " " + alias + " " for alias in aliases for v in variants)
                if not fragment:
                    found.add(phrase)
        counts.update(found)
    # These are unvalidated phrases, never silently folded into a known concept.
    singular = {"algebras": "algebra", "groups": "group", "groupoids": "groupoid", "equations": "equation", "modules": "module"}
    return {phrase: [phrase, phrase.rsplit(" ", 1)[0] + " " + singular.get(phrase.rsplit(" ", 1)[-1], phrase.rsplit(" ", 1)[-1])]
            for phrase, n in counts.items() if n >= 2}


def extract_concepts(publications, researchers, vocabulary=None):
    vocabulary = vocabulary if vocabulary is not None else load_vocabulary()
    auto = discover_phrases([p["title"] for p in publications if not p.get("quarantined") and not p.get("is_retracted")], vocabulary)
    terms = {**auto, **vocabulary}
    compiled = {label: [re.compile(r"(?<!\w)" + re.escape(normalise(a)) + r"(?!\w)")
                        for a in set([label, *aliases])]
                for label, aliases in terms.items()}
    documents = []
    for p in publications:
        if p.get("is_retracted") or p.get("quarantined"):
            continue
        for field in ("title", "abstract"):
            if p.get(field):
                documents.append((p["id"], field, p[field], source_for(p, field)))
    for r in researchers:
        if r.get("status") == "verified":
            for desc in r.get("profile", {}).get("descriptions", []):
                documents.append(("researcher:" + r["id"], "research_description", desc["text"], desc["source"]))
    concepts, mentions = {}, []
    for owner, field, text, url in documents:
        clean = normalise(text)
        matches = []
        for label, patterns in compiled.items():
            hits = [(m.start(), m.end(), m.group()) for pattern in patterns for m in pattern.finditer(clean)]
            if hits:
                matches.append((label, sorted(hits, key=lambda h: h[1] - h[0], reverse=True)[0]))
        for label, (start, end, phrase) in matches:
            if label == "braces":
                skew_spans = [m.span() for pattern in compiled.get("skew braces", []) for m in pattern.finditer(clean)]
                standalone = [m for pattern in compiled[label] for m in pattern.finditer(clean)
                              if not any(s <= m.start() and e >= m.end() for s, e in skew_spans)]
                if not standalone:
                    continue
                phrase = standalone[0].group()
            cid = stable_id("concept", normalise(label))
            validated = label in vocabulary
            concepts[cid] = {"id": cid, "label": label, "kind": "concept",
                             "terminology_status": "normalised_vocabulary" if validated else "unvalidated_extracted_phrase",
                             "aliases": terms[label]}
            mentions.append({"owner": owner, "concept": cid, "field": field,
                **evidence(url, "normalised_phrase_match" if validated else "recurring_mathematical_title_phrase",
                           excerpt(text, phrase), 0.9 if validated else 0.55,
                           matched_phrase=phrase, reliability="explicit_text", status="extracted")})
    return concepts, mentions


def tfidf_vectors(texts):
    """Smoothed IDF and L2 normalisation, implemented without a model download."""
    counters = []
    for text in texts:
        tokens = [t for t in normalise(text).split() if len(t) > 2 and t not in STOP]
        terms = tokens + [a + " " + b for a, b in zip(tokens, tokens[1:])]
        counters.append(Counter(terms))
    df = Counter(term for counter in counters for term in counter)
    result = []
    for counter in counters:
        weights = {term: (1 + math.log(count)) * (1 + math.log((1 + len(texts)) / (1 + df[term])))
                   for term, count in counter.items()}
        norm = math.sqrt(sum(w * w for w in weights.values())) or 1
        result.append({t: w / norm for t, w in weights.items()})
    return result


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return min(1.0, sum(value * b.get(key, 0) for key, value in a.items()))


def related_concepts(concepts, mentions):
    by_publication = {}
    for m in mentions:
        if not m["owner"].startswith("researcher:"):
            by_publication.setdefault(m["owner"], set()).add(m["concept"])
    owners = {cid: {pid for pid, found in by_publication.items() if cid in found} for cid in concepts}
    edges = []
    for a, b in combinations(sorted(concepts), 2):
        shared = sorted(owners[a] & owners[b])
        if not shared:
            continue
        weight = len(shared) / math.sqrt(len(owners[a]) * len(owners[b]))
        edges.append({"id": stable_id("related", a, b), "source_id": a, "target_id": b,
            "type": "RELATED_TO", "status": "candidate", "reliability": "candidate",
            "method": "publication_cooccurrence_cosine", "confidence": round(weight, 4),
            "source": sorted({m["source"] for m in mentions if m["owner"] in shared and m["concept"] in {a, b}}),
            "evidence": {"publication_ids": shared, "count": len(shared),
                "explanation": "Co-occurrence suggests a topic association; it does not establish a mathematical implication."},
            "review_status": "unreviewed"})
    return edges
