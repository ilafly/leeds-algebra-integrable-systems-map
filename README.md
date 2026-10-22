# Leeds Algebra and Integrable Systems Knowledge Map

A working local research prototype for finding evidence-based mathematical connections across the Leeds algebra and integrable systems research community. The original three-person pilot has been expanded to **15 researchers** in `config/researchers.toml`. Python 3.11+, Streamlit, NetworkX, SQLite and PyVis; no paid AI API, model download or graph database.

The included dataset uses **453 publication records in discovery, 395 with abstracts**, collected through verified identities, OpenAlex, ORCID, Crossref and arXiv. A total of 480 identifier-deduplicated records are retained; 27 are quarantined pending independent authorship corroboration. The system scores all 105 researcher pairs. The [evidence report](reports/discovered_connections.md) contains the current topic count, coverage, possible duplicate versions and uncertainty. Fourteen ORCIDs are independently corroborated; Oleg Chalykh's ORCID remains explicitly labelled OpenAlex-reported. The roster includes former and joint affiliations and is not a current Leeds employment directory.

Validation includes ingestion and Unicode name safeguards, graph construction, filters, persistent reviews, batched metadata lookup and exclusion of uncorroborated authorship. The actual Streamlit app executes all three map views with the expanded dataset and filters for the new researchers. Its original HTTP health check returned `ok`. Canvas rendering and physical graph clicks have not been visually verified.

## Launch

From this project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open **http://127.0.0.1:8501**. The included `data/snapshot.json` is a real, retrieved dataset, so the application works without research API access. On this machine the required libraries are already installed and `python3 -m streamlit run app.py` also works directly. The app binds to loopback and does not collect metadata on page load.

## Collect and reproduce

```bash
# Verify identities, collect up to 40 recent works per researcher and enrich exact IDs.
python -m kgmap.cli collect

# Quicker initial collection: OpenAlex publications plus profile/ORCID identity checks.
python -m kgmap.cli collect --skip-enrichment

# Expand the sample; cached successful responses are reused for 30 days.
python -m kgmap.cli collect --limit 80

# Explicit refresh, with failures and stale-cache fallback recorded.
python -m kgmap.cli collect --refresh

# Rebuild the vocabulary extraction, graph inputs and report without network access.
python -m kgmap.cli analyse

# Repeat collection using only previously cached responses.
python -m kgmap.cli collect --offline

# Regenerate the report and identity table.
python -m kgmap.cli report

python -m pytest -q
```

Commands are independent and may be rerun. Use `--config PATH`, `--database PATH`, and `--limit N` to control the pilot. A collection with no publications preserves the previous snapshot and writes `data/collection_attempt.json`. Exit codes: 0 success, 1 no publications, 2 partial collection with unresolved identities. Source failures during supplementary enrichment are reported without discarding retrieved records.

If OpenAlex requires a free API key in your environment, set `OPENALEX_API_KEY` as an environment variable. The collector works without a key when anonymous access is available. Keys are excluded from cached URLs, provenance and logs. You can set a contact address in `[collection]` for the descriptive user agent. Requests use certificate verification, timeouts, per-host pacing and bounded retries; arXiv requests are at least 3.1 seconds apart. Uncached arXiv IDs are queried in batches of up to 25, while existing individual responses remain reusable. Public page retrieval checks robots.txt. Never disable TLS verification to work around a local certificate configuration problem.

## Explore

- **Knowledge map:** concept nodes and dashed candidate co-occurrence edges. A vocabulary match identifies terminology, not a theorem.
- **Researcher network:** solid green coauthorship and separate dashed purple thematic proximity edges.
- **Integrated map:** researchers, publications and concepts joined through the original metadata and text evidence.
- Click a graph node or edge to inspect its full record and source links in the panel beneath the graph. Drag nodes and scroll to zoom. The dropdown inspector also lists a researcher's topics or the researchers associated with a topic.
- Filter by researcher, concept, publication year, relationship type and candidate threshold. Publication filters **recompute** topic associations and researcher scores. Dated views omit undated profile descriptions and undated papers.
- Select two researchers to highlight an evidence-bearing path. Use the integrated map to see the complete path. The search honours the visible relationship types, date range, threshold and rejected reviews, and excludes the direct thematic shortcut.
- The **Candidate connections** tab gives score components, topic bridges, abstract pairs, supporting publications, links and uncertainty.
- **Identity & sources** shows identity decisions, rejected namesakes, provider failures and HTTP cache use.
- **Review** accepts, rejects or annotates corrections to researcher candidates, concept associations and text extractions. Rejected text extractions and associations are excluded before scores are recomputed. Review decisions remain in SQLite across refreshes. A correction note preserves the original edge for audit; reject it to exclude it, or change the vocabulary and reanalyse to correct terminology.

The local graph embeds the graph library's JavaScript, so rendering does not require a graph CDN. Generated HTML uses text-only inspection of untrusted metadata and validates source link schemes.

## Scientific method and limits

Identity resolution combines configured name aliases, public researcher pages, exact ORCID links where available, and exact affiliations in OpenAlex. More than one eligible author cluster, conflicting identifiers or insufficient independent evidence produces `needs_review`; collection for that person stops. A configuration identifier alone cannot verify someone. Automated bibliographic identity verification does not certify every publication in an OpenAlex cluster.

Names retain non-Latin characters during identity matching, including the Cyrillic OpenAlex name associated with Alexander Mikhailov's verified ORCID. Public ORCID names **and** employment records can corroborate a configured identifier when an HTML profile is missing. Historical employment verifies bibliographic identity without asserting a current position. `affiliation_note` and `affiliation_source` document former or joint appointments in the identity table.

Alison Parker's OpenAlex cluster mixes mathematics with apparent psychology and chemistry namesakes. Her configuration therefore sets `require_publication_corroboration = true`: an assignment needs an exact work identifier in her public ORCID bibliography or an exact publisher-supplied ORCID. Uncorroborated assignments remain in `authorship_reviews` and `unverified_researcher_ids`; an otherwise unassigned publication is marked `quarantined` and excluded from concept extraction, TF-IDF, collaborations and paths. A coauthor whose identity is independently resolved can retain the same publication. The source tab and report list held assignments; absence from an ORCID bibliography is not proof of non-authorship. Twelve of Alison's retrieved records meet the corroboration rule in this snapshot.

Six supplementary DOI lookups return Crossref 404 responses; their OpenAlex/arXiv metadata remain available. Source failures and authorship-review issues are recorded separately in the app.

Collection queries the verified OpenAlex author ID, checks returned authorship IDs, and stores titles, abstracts when available, authors, dates, DOIs, URLs, licences and provenance. ORCID public records supplement identity evidence. An ORCID supplied only by OpenAlex is labelled reported, independently of the verified OpenAlex identity; it is not silently promoted to independently verified ORCID. Crossref enrichment uses exact DOI lookups, skipping arXiv's DataCite DOI prefix; arXiv uses exact identifiers supplied by retrieved records, never an ambiguous author-name query. DOI aliases, arXiv ID and OpenAlex ID are deduplication keys. arXiv's explicit journal DOI can connect a preprint to its journal record, with both identifiers retained. Identical titles alone do not merge records. Pilot coauthors are recognised by verified author IDs even when a joint work falls outside another person's retrieval window.

Concept extraction uses a small editable terminology vocabulary, Unicode/hyphen normalisation and word-boundary matches. Repeated title phrases ending in mathematical nouns discover additional **unvalidated** terms. Generic words such as “model” and “structure” are excluded. Skew braces, braces, matched pairs, matched products, mapping class groups and mapping class groupoids remain distinct. The vocabulary supplies **no edges**.

The transparent thematic ranking is:

```text
0.40 × IDF-weighted Jaccard similarity of researcher concept sets
+ 0.20 × mean of strongest 3 nonidentical concept co-occurrence bridges
+ 0.30 × mean of strongest 3 independent publication abstract TF-IDF cosines
+ 0.10 × strongest 2-hop concept path through an intermediate concept
```

TF-IDF uses unigrams and bigrams, log term frequencies, smoothed IDF and L2 normalisation. Joint publications are excluded from abstract comparisons so they do not inflate the independent language signal. Missing components contribute zero; weights are not renormalised. Shared collaborators use stable author IDs and are reported as social evidence separately from thematic ranking. Coauthorship is not included in the mathematical score.

This is an exploratory ranking, **not** a probability, mathematical implication or novelty assessment. `RELATED_TO` records only candidate co-occurrence. `GENERALISES`, `SPECIAL_CASE_OF` and `USES_METHOD` are reserved for explicit supported mathematical assertions; this pilot does not infer them from similarity. Acceptance records a review decision and never relabels a candidate as a theorem. Numeric extraction confidence is an uncalibrated reliability hint. Recurring terminology, incomplete abstracts, a small sample and provider clustering errors affect the results.

Automated tests check software safeguards. Scientific validation still needs mathematician-labelled examples and precision/recall and usefulness evaluations; no scientific accuracy metric has been established.

## Add a researcher

Add a `[[researchers]]` block to `config/researchers.toml`:

```toml
[[researchers]]
id = "a-stable-unique-slug"
name = "Full Name"
aliases = ["Published Name Variant"]
affiliation = "Exact Institution Name"
profile_url = "https://university.example/staff/person"
homepage_url = "https://person.example/"
# orcid = "....-....-....-...."  # only if corroborated by a public source
```

Use stable IDs so reviews survive configuration changes. Run `python -m kgmap.cli collect`; inspect the identity table before interpreting the graph. If an identity is unresolved, inspect the recorded candidates and add a documented name alias or an identifier linked by the person's page, then retry. Do not bypass a conflict with a name-only match. The initial collector expects public HTML researcher pages; JavaScript-only or bot-blocked pages need another corroborating public source or a future reviewed identity-override workflow.

Edit `config/vocabulary.json` to validate new terms or refine equivalent terminology. Do not put mathematical implications or researcher relationships there. Run `analyse` after vocabulary changes.

## Review portability

```bash
python -m kgmap.cli export-reviews --file data/reviews.json
# Edit status: unreviewed, accepted, rejected or corrected; add a note for corrections.
python -m kgmap.cli import-reviews --file data/reviews.json
```

Import validates the complete file before changing any decisions. Reviews are keyed by stable researcher pairs or source/concept/field IDs. Scores can change while a review persists; re-evaluate older reviews when the underlying evidence changes. The app exports the currently visible graph as NetworkX node-link JSON and the full dataset evidence report as Markdown.

## Files

```text
app.py                           Streamlit application
config/researchers.toml           Collection settings and extensible researcher roster
config/vocabulary.json           Terminology aliases; no predefined relationships
kgmap/cli.py                     Reproducible collection / analysis / report commands
kgmap/sources.py                 Profile, OpenAlex, ORCID, Crossref, arXiv and deduplication
kgmap/http.py                    Paced, retrying HTTP with SQLite cache and provenance log
kgmap/concepts.py                Phrase extraction, normalisation and TF-IDF
kgmap/connections.py             Explained candidate ranking and collaboration evidence
kgmap/graph.py                   NetworkX graph, filtered recomputation and evidence paths
kgmap/store.py                   SQLite cache, snapshot and persistent reviews
kgmap/visualisation.py           Offline-capable interactive graph rendering
data/snapshot.json               Portable real-data snapshot
data/map.sqlite                  Local cache and reviews (Git ignored)
reports/researcher_identities.csv Identity verification table
reports/discovered_connections.md Automatically generated evidence report and source issues
tests/                          Synthetic unit fixtures only; not demonstration app data
```

Metadata provenance includes source/provider, fields and processing timestamps. The snapshot's collection request log records actual HTTP retrieval/cache timestamps and any use of stale cached responses. Publication dates come from providers; a preprint and journal manifestation may have different dates. Matching-title records without a shared reliable identifier remain separate and are flagged for version review in the report and source tab. Publication and coauthorship counts therefore count records and may include unlinked versions. OpenAlex metadata are CC0; abstracts and other source content retain their respective licences. This local pilot does not download full papers. Review source terms before redistributing cached abstracts or expanding collection substantially.

The next development priorities are manual scientific evaluation, improved handling of split/contaminated author clusters and preprint versions, reviewed explicit mathematical assertions, and better extraction of mathematical notation. Current extraction can miss LaTeX-heavy phrases and does not resolve negation or prove mathematical relationships.
