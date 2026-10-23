# Leeds Algebra and Integrable Systems Knowledge Map

A research prototype investigating how mathematical knowledge and scientific collaboration can be studied together within a local scientific community. The project combines automatic discovery from research outputs with source inspection and expert review. Its initial case study is the Leeds Algebra and Integrable Systems group at the University of Leeds.

## Scientific motivation and conceptual framework

### Two interconnected structures

Research communities are organised around the knowledge they produce and the relationships between the people who produce it. These structures do not necessarily coincide. Researchers may work on closely related mathematical problems without having collaborated, while established collaborators may bring different methods and perspectives to a shared project.

This project asks whether combining a **mathematical knowledge graph** with a **social collaboration network** can give a richer account of a scientific community and suggest connections that are not apparent from its existing collaborations. The aim is to understand how research directions coexist, interact and potentially complement one another. It is not to rank individual researchers or measure research performance.

The framework draws on work on knowledge graphs (Hogan et al., 2021), scientific collaboration networks (Newman, 2001) and multilayer networks (Kivelä et al., 2014). The distinction between kinds of relationship remains essential when bringing these perspectives together.

### Leeds as a local scientific community

The Leeds Algebra and Integrable Systems group provides a bounded local case study embedded in a wider scientific network. A shared organisational setting makes the sample manageable and gives researchers a context in which to interpret proposed connections and assess their mathematical usefulness.

The community's boundaries are organisational rather than intellectual. Its members collaborate internationally, and the concepts relevant to their work extend beyond the group. The configured roster is a research sample that includes former and joint affiliations, rather than a directory of current Leeds employees. Studying this local community therefore does not assume that its mathematical interests or professional relationships form a closed network.

### The mathematical knowledge graph

A knowledge graph represents things and the relationships between them. In the mathematical component, the things of interest are concepts, theories, methods and problems. These are represented by points, called **nodes**, while named links, called **edges**, describe their relationships.

A relationship can be written as a semantic triple: **Subject — Predicate — Object**. For example, one mathematical structure may *generalise* another, a theorem may *concern* a class of objects, or a method may be *used to investigate* a problem. These examples describe the kinds of explicit mathematical relationships the research programme aims to represent.

The current implementation constructs a lightweight graph by extracting mathematical terminology from publications and research descriptions and normalising spelling and terminology variants. Its automatically generated links between concepts record candidate associations based on their occurrence in the same publications. **A textual association is distinct from an established mathematical relationship.** Similar language or shared terminology does not establish a generalisation, implication or applicable method.

A domain ontology—a controlled vocabulary with explicit definitions of concepts and relationship types—is a longer-term goal. The present terminology vocabulary helps recognise terms; it does not supply mathematical relationships. Automatic extraction of theorems and their logical relationships is not implemented.

### The social collaboration network

The social component represents researchers as nodes and documented collaborations as edges. Social network analysis studies patterns in these relationships: for example, which researchers are connected through collaborators, which form closely connected groups, and which link different parts of a community.

The prototype currently records coauthorship from publication metadata and reports shared external collaborators where stable author identifiers are available. Participation in joint projects and other documented forms of scientific collaboration would extend this evidence in future work. A submitted suggestion about joint work remains a contribution for review until its evidence is incorporated.

An absent collaboration edge means that no collaboration was recovered from the available sample. It does not establish that two researchers have never worked together, nor that they lack shared interests. Coauthorship is evidence of a social relationship; it does not by itself establish mathematical similarity.

### Connecting knowledge and collaboration

The integrated graph connects three principal kinds of entity:

- **Researchers**, representing members of the scientific community.
- **Publications**, providing documented evidence of research activity.
- **Mathematical concepts**, representing terminology extracted from that activity.

Authorship connects researchers to publications, and concept extraction connects publications to mathematical topics. For example, two researchers' separate publications may discuss the same concept, providing an inspectable path between them even when the sample contains no joint paper. Every step has a different meaning: authorship, a topic mention and a candidate concept association must be interpreted accordingly.

This supports a comparison between **social proximity**, currently described through recorded coauthorship and shared collaborators, and **intellectual proximity**, estimated through shared topics, associations between topics and similarities between independent papers. The current thematic score keeps coauthorship separate from its mathematical signals.

Researchers with few observed social links may share mathematical interests, while collaborators may connect distinct mathematical areas. Inspecting paths through the integrated graph is intended to suggest shared structures, potential bridges between research directions and opportunities for collaboration. Such a path supplies a reason to investigate a connection; its mathematical significance requires expert judgement.

### Automatic discovery and expert validation

The research task is to discover useful candidate relationships from evidence, explain them and assess them with mathematicians. The maps provide a way to inspect that process. The prototype already combines automatic concept extraction, terminology normalisation, text similarity and paths through concept associations to generate candidates. Its current thematic arcs require at least one shared extracted topic.

Proposed connections should be traceable to identifiable concepts, supporting publications and source excerpts, including PDF page evidence where available. The system distinguishes bibliographic evidence, automatically extracted terminology and computational hypotheses. A concept mentioned in background discussion may not describe an author's own contribution, and a high similarity score may have little mathematical significance.

Expert review is therefore an essential part of the methodology. The app provides tools for inspecting evidence, accepting or rejecting candidates, recording corrections and submitting missing evidence. These tools support validation; they do not demonstrate that the discovered connections have been scientifically validated. A systematic evaluation using mathematician-labelled examples, measures of missed and incorrect connections, and assessments of usefulness remains to be carried out. Accepting a candidate records a review decision without turning a similarity-based association into a theorem.


### Scope and research status

The maps represent relationships recoverable from the available sources, rather than the complete mathematical knowledge or professional relationships of individuals. Publication metadata may be incomplete, identities may be ambiguous and mathematical terminology may have several meanings. The project prioritises provenance, interpretability, reproducibility and human validation in handling these limitations.

The current prototype supports evidence collection, candidate discovery, graph exploration and review. A formal domain ontology, explicit supported mathematical assertions, broader collaboration-network analysis such as community detection, and systematic studies of change over time remain research goals. Date filters and repeatable collection provide useful tools, but do not constitute a completed longitudinal study. The system is an exploratory research tool, not an authoritative assessment of researchers or scientific communities.

### References

- Hogan, A. et al. (2021). *Knowledge Graphs*. ACM Computing Surveys, 54(4), Article 71. [https://doi.org/10.1145/3447772](https://doi.org/10.1145/3447772)
- Newman, M. E. J. (2001). *The structure of scientific collaboration networks*. Proceedings of the National Academy of Sciences, 98(2), 404–409. [https://doi.org/10.1073/pnas.98.2.404](https://doi.org/10.1073/pnas.98.2.404)
- Kivelä, M. et al. (2014). *Multilayer networks*. Journal of Complex Networks, 2(3), 203–271. [https://doi.org/10.1093/comnet/cnu016](https://doi.org/10.1093/comnet/cnu016)

## Current prototype

The original three-person pilot has been expanded to **15 researchers** in `config/researchers.toml`. Python 3.11+, Streamlit, NetworkX, SQLite and PyVis; no paid AI API, model download or graph database.

The included dataset uses **453 publication records in discovery, 395 with abstracts**, collected through verified identities, OpenAlex, ORCID, Crossref and arXiv. A total of 480 identifier-deduplicated records are retained; 27 are quarantined pending independent authorship corroboration. The system scores all 105 researcher pairs; thematic arcs and candidate listings require at least one shared extracted topic. The [evidence report](reports/discovered_connections.md) contains the current topic count, coverage, possible duplicate versions and uncertainty. Fourteen ORCIDs are independently corroborated; Oleg Chalykh's ORCID remains explicitly labelled OpenAlex-reported. The roster includes former and joint affiliations and is not a current Leeds employment directory.

Full-text analysis adds page-linked topic evidence and a separate body-text similarity signal. The first balanced sample of **30 attempted papers** yielded **28 usable PDFs, covering all 15 researchers and 842 pages**, with 156 page-linked topic mentions. Successful coverage and the two access failures are listed in the [evidence report](reports/discovered_connections.md). PDFs and extracted pages remain local in `data/fulltext/`, outside Git. The app can switch back to the title, abstract and profile baseline.

Software checks cover ingestion and Unicode name safeguards, graph construction, filters, persistent reviews, batched metadata lookup, PDF extraction safeguards and exclusion of uncorroborated authorship. The actual Streamlit app executes all three map views with the expanded dataset and filters for the new researchers. Its original HTTP health check returned `ok`. Canvas rendering and physical graph clicks have not been visually verified.

## Launch

From this project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open **http://127.0.0.1:8501**. The included `data/snapshot.json` is a real, retrieved dataset, so the application works without research API access. Full-text evidence additionally requires its local `data/fulltext/` cache; a checkout without that cache automatically recomputes the app view from available metadata. Uploaded originals and suggestion attachments also need `data/uploads/` for downloads. Use the virtual environment for PDF extraction, which requires `pypdf`. The app binds to loopback and does not collect metadata on page load.

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

# Fetch a balanced sample of 30 public PDFs, extract text and rebuild the analysis.
python -m kgmap.cli fulltext --max-papers 30

# Attempt every candidate with a source-supplied open-access PDF link or arXiv ID.
python -m kgmap.cli fulltext --max-papers 0

# Rebuild the title/abstract/profile baseline; cached PDFs remain available.
python -m kgmap.cli analyse --metadata-only

# Repeat collection using only previously cached responses.
python -m kgmap.cli collect --offline

# Regenerate the report and identity table.
python -m kgmap.cli report

python -m pytest -q
```

Commands are independent and may be rerun. Use `--config PATH`, `--database PATH`, and `--limit N` to control the pilot. A collection with no publications preserves the previous snapshot and writes `data/collection_attempt.json`. Exit codes: 0 success, 1 no publications, 2 partial collection with unresolved identities. Source failures during supplementary enrichment are reported without discarding retrieved records.

If OpenAlex requires a free API key in your environment, set `OPENALEX_API_KEY` as an environment variable. The collector works without a key when anonymous access is available. Keys are excluded from cached URLs, provenance and logs. You can set a contact address in `[collection]` for the descriptive user agent. Requests use certificate verification, timeouts, per-host pacing and bounded retries; arXiv metadata requests are at least 3.1 seconds apart. Uncached arXiv IDs are queried in batches of up to 25, while existing individual responses remain reusable. Public page and PDF retrieval check robots.txt; PDF requests respect its crawl delay, currently 15 seconds on arXiv. Never disable TLS verification to work around a local certificate configuration problem.

The full-text stage uses OpenAlex's source-supplied open-access PDF locations and exact arXiv identifiers already attached to verified publications. It skips quarantined and retracted records and tries at most three locations per selected paper. There is no paywall bypass or name-based paper matching. Attempts are selected round robin, recent first, without choosing a joint record twice. A balance of attempts cannot guarantee equal successful coverage. `[full_text]` configures the default sample and limits (20 MB, 200 pages, at least 200 body words). Oversized papers are reported rather than silently truncated.

`pypdf` extracts every page and corroborates the title against the first two pages. The analysis removes detected reference sections, subsequent content and repeated short headers; original page text is retained for inspection. Image-only or very sparse extractions are marked `needs_ocr_or_review` and excluded. No OCR runs automatically. PDF reading order, formulas, word spacing and undetected bibliographies remain limitations. Each ready document records its source, version/licence when supplied, SHA-256, extraction method and retrieval times. Existing successful artifacts are reused without network access and retained across metadata refreshes; `fulltext --refresh` retries public sources while preserving uploaded files. `--offline` uses only cached responses and artifacts.

## Upload missing PDFs

In **Publications → Upload a missing PDF**, select the existing publication, choose a PDF and click **Upload PDF and update analysis**. The list includes failed downloads, papers not yet attempted, and records whose local PDF or usable text is missing. Files are limited to 20 MB and 200 pages by default. A readable PDF must match the selected publication's title before its text is analysed. Usable text updates topic evidence, similarity scores and the report; scans are saved for OCR or review and excluded from analysis. An identical file can restore a lost original without duplicating the upload history. Uploading a file preserves the publication's existing identifiers, authorship and review decisions.

For a paper missing from the map entirely, attach its PDF to a **Suggestions** submission. The file remains pending for review; it does not create a verified publication or coauthorship relationship. A reviewer can use **Use attachment for a paper already in the map** to match it to an existing eligible record, with another title check before analysis.

Uploaded originals use content hashes as filenames under the Git-ignored `data/uploads/` directory. The active paper's extracted pages live in `data/fulltext/`; the snapshot holds only provenance and short evidence snippets. Uploaded sources retain their filename, SHA-256, upload time and explicit upload origin. The app offers **Download cached PDF** in a paper's **Full text and page evidence** expander, and **Download attached PDF** in the suggestion queue. Back up both directories and `data/map.sqlite` to preserve the files, extracted text, suggestions and reviews together.

## Explore

- **Knowledge map:** concept nodes and dashed candidate co-occurrence edges. A vocabulary match identifies terminology, not a theorem.
- **Researcher network:** solid green coauthorship and separate dashed purple thematic proximity edges.
- Dotted candidate links get thicker as their score increases. Width uses the fixed rule `1.2 + 6 × score` pixels on the 0–1 score range, across all filters and views. A highlighted path adds 2 pixels while preserving score differences. Concept-association and researcher scores use different heuristics; inspect the numeric score before comparing them.
- **Integrated map:** researchers, publications and concepts joined through the original metadata and text evidence. Turn off **Show papers** to see researchers and concepts directly connected by **Papers mention topic** links. Each such link summarises the retained authorship and topic evidence, counting each supporting paper once; it does not assert expertise. Supporting papers and excerpts remain available in the relationship inspector. Hiding papers changes the display, while scores continue to use the same publication sample. Relationship filters, path highlighting and the visible graph export follow the selected display.
- Hover over a graph link for its meaning, score and review status. Click it to see a readable explanation, supporting paper titles, source excerpts with PDF page links, and the calculation behind its score. Concept associations explain their publication counts and normalisation; researcher candidates show weighted components, shared topics, bridges and independent paper comparisons. Raw records and provenance remain available in a disclosure beneath the explanation.
- Turn on **Show relationship labels** to put plain relationship names, paper counts or candidate scores on the links, such as “Mentions topic”, “Together in 5 papers” or “Thematic candidate: 0.177”. “Together” means both topics occur in those papers; it does not assert a mathematical relationship. Labels use horizontal text and print once for repeated text fields on the same link; exact fields and PDF pages remain in the inspector. Coauthorship and thematic links between the same researchers remain separate curves. Dense maps start with labels off. **Inspect a relationship** provides a searchable selector for exactly the links in the current map, respecting date, researcher, concept, relationship-type, score and review filters. It initially shows five supporting papers; **Show all supporting papers** expands the complete set.
- Click a node to inspect its record and source links. Drag nodes and scroll to zoom. The node dropdown also lists a researcher's topics or the researchers associated with a topic.
- Filter by researcher, concept, publication year, relationship type and candidate threshold. Publication filters **recompute** topic associations and researcher scores. Dated views omit undated profile descriptions and undated papers.
- A thematic researcher arc requires **at least one shared extracted topic**, plus a positive score meeting the threshold. Positive text similarity, bridges or indirect paths alone cannot create an arc. The same rule applies to the candidate list, relationship inspector, graph export and report. Authorship and coauthorship remain separate bibliographic relationships. All pair calculations are retained in the snapshot for audit, including pairs omitted from thematic display.
- Select two researchers to highlight an evidence-bearing path. Use the integrated map to see the complete path. The search honours the visible relationship types, date range, threshold and rejected reviews, and excludes the direct thematic shortcut.
- The **Candidate connections** tab gives score components, topic bridges, abstract and full-text pairs, supporting publications, links and uncertainty. Full-text coverage is shown for each pair.
- **Publications** searches cached body text as well as metadata. Open **Full text and page evidence** to read extracted pages and follow a page-specific source PDF link. The sidebar's **Include available full text** toggle recomputes the graph and scores for comparison with the metadata baseline.
- **Identity & sources** shows identity decisions, rejected namesakes, provider failures and HTTP cache use.
- **Review** accepts, rejects or annotates corrections to researcher candidates, concept associations and text extractions. Rejected text extractions and associations are excluded before scores are recomputed. Review decisions remain in SQLite across refreshes. A correction note preserves the original edge for audit; reject it to exclude it, or change the vocabulary and reanalyse to correct terminology.
- **Suggestions** records missing joint work, papers, possible connections, corrections and general feedback, with a source and a review history.

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
0.60 × IDF-weighted Jaccard similarity of researcher concept sets
+ 0.15 × mean of strongest 3 nonidentical concept co-occurrence bridges
+ 0.20 × mean of strongest 3 independent publication abstract TF-IDF cosines
+ 0.05 × strongest 2-hop concept path through an intermediate concept
```

When full text is enabled and the visible sample contains usable local text, the fixed weights are **0.55 shared topics / 0.15 topic bridges / 0.15 abstract similarity / 0.05 intermediate paths / 0.10 full-text similarity**. Full-text similarity is the mean of the strongest three independent body-text TF-IDF cosines. Full-text topic mentions also extend the concept evidence. The app and report show the weights actually used; samples without full text use the metadata formula above.

The `shared-topics-v2` revision assigns more than half the weight to direct topic overlap and reduces the effect of language similarity and indirect paths. These fixed weights are an exploratory choice, not an empirically calibrated measure. A pair with zero shared topics is excluded from thematic display regardless of its other scores. The shared-topic rule is re-evaluated after filters, full-text selection and rejected extractions are applied. Review IDs persist across the revision; earlier decisions may need reassessment against the new evidence and scores.

TF-IDF uses unigrams and bigrams, log term frequencies, smoothed IDF and L2 normalisation, with separate corpora for abstracts and paper bodies. Joint publications are excluded from both language comparisons so they do not inflate the independent language signal. Missing components contribute zero; weights are not renormalised, so unequal full-text coverage affects rankings. Topic matches in background discussion are not proof of expertise. Shared collaborators use stable author IDs and are reported as social evidence separately from thematic ranking. Coauthorship is not included in the mathematical score.

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

## Suggestions

Open **Suggestions**, choose a type, select the researchers involved, and add a title and explanation. A **Joint work** suggestion needs at least two researchers in this map and a source URL, DOI, attached PDF or existing paper. Use **Missing paper** for a paper involving one researcher in the map and external coauthors. The contributor's name is optional. Invalid submissions keep the draft available for correction.

The queue can be filtered by researcher and status: pending, under review, accepted for follow-up, resolved or rejected. Add a review note when resolving or rejecting a suggestion. The original submission and every review event remain in its history; **Export all suggestions** downloads the queue as JSON, including attachment metadata. Download PDF attachments separately. Accepted means ready for follow-up. A checked PDF can be analysed against an existing publication through the attachment controls. New bibliographic records and terminology changes still need collection or vocabulary editing; suggestion status changes do not add verified authorship or alter scores automatically.

Suggestions are stored independently of the research snapshot in the app's local SQLite database, so collection and analysis refreshes preserve them. People using the same running app share this queue. Separate installations keep their own queues; the JSON export provides a portable copy. Suggestions stay outside the portable scientific snapshot and the evidence report until their evidence is incorporated.

## Files

```text
app.py                           Streamlit application
config/researchers.toml           Collection settings and extensible researcher roster
config/vocabulary.json           Terminology aliases; no predefined relationships
kgmap/cli.py                     Reproducible collection / analysis / report commands
kgmap/sources.py                 Profile, OpenAlex, ORCID, Crossref, arXiv and deduplication
kgmap/http.py                    Paced, retrying HTTP with SQLite cache and provenance log
kgmap/fulltext.py                Public PDF retrieval, title checks and page-aware extraction
kgmap/uploads.py                 Local PDF validation, provenance, storage and analysis
kgmap/upload_ui.py               Missing-PDF uploads, downloads and attachment matching
kgmap/concepts.py                Phrase extraction, normalisation and TF-IDF
kgmap/connections.py             Explained candidate ranking and collaboration evidence
kgmap/graph.py                   NetworkX graph, filtered recomputation and evidence paths
kgmap/store.py                   SQLite cache, snapshot, reviews and suggestions
kgmap/suggestions.py             Suggestion validation and source normalisation
kgmap/suggestion_ui.py           Submission form, review queue, history and export
kgmap/visualisation.py           Offline-capable interactive graph rendering
kgmap/inspection.py              Source-grounded relationship explanations and score details
kgmap/inspection.js              Safe, structured graph click inspector
data/snapshot.json               Portable real-data snapshot
data/map.sqlite                  Local cache and reviews (Git ignored)
data/fulltext/                   Original PDFs and page text JSON (local, Git ignored)
data/uploads/                    Uploaded PDFs and suggestion attachments (local, Git ignored)
reports/researcher_identities.csv Identity verification table
reports/discovered_connections.md Automatically generated evidence report and source issues
tests/                          Synthetic unit fixtures only; not demonstration app data
```

Metadata provenance includes source/provider, fields and processing timestamps. The snapshot's collection request log records actual HTTP retrieval/cache timestamps and any use of stale cached responses. Publication dates come from providers; a preprint and journal manifestation may have different dates. Matching-title records without a shared reliable identifier remain separate and are flagged for version review in the report and source tab. Publication and coauthorship counts therefore count records and may include unlinked versions. OpenAlex metadata are CC0; abstracts and public PDFs retain their respective licences. Whole-paper text is kept out of the portable snapshot and exported report; source terms govern redistribution of cached content.

The next development priorities are manual scientific evaluation, improved handling of split/contaminated author clusters and preprint versions, reviewed explicit mathematical assertions, and better extraction of mathematical notation. Current extraction can miss LaTeX-heavy phrases and does not resolve negation or prove mathematical relationships.
