# Charaka Samhita Chunking

## Raw Input Format

The parser receives individual JSON files from `books/charak_samhita/`. Each file is a Semantic MediaWiki export with this structure:

```json
{
  "title": "Agni",
  "url": "https://charakasamhita.com/index.php?title=Agni",
  "text": "Full page text content...",
  "html": "<p>HTML content...</p>",
  "outgoing_links": [
    "https://charakasamhita.com/index.php?title=Agni_mahabhuta",
    "https://charakasamhita.com/index.php?title=Pachaka_pitta"
  ]
}
```

## Parsing Structure — Two-Pass Architecture

### Pass 0: High-Level Hierarchy

`CharakaSamhita_chunking/main.py::main()` manually creates:

1. **Treatise Root** node with ID from `parser.hierarchy.root_id` (UUID v5 of `"root_charaka_samhita"`), level `"book"`.
2. **8 Sthana nodes** with IDs from `parser.hierarchy.sthana_ids`:
   - Sutra_Sthana, Nidana_Sthana, Vimana_Sthana, Sharira_Sthana, Indriya_Sthana, Chikitsa_Sthana, Kalpa_Sthana, Siddhi_Sthana
   - Level: `"sthana_index"`, parent: treatise root
3. **Meta Hub** (Appendices & Meta), ID from `parser.hierarchy.meta_hub_id`.
4. **Materia Medica** node, ID from `parser.hierarchy.materia_medica_id`.

### Pass 1: Discovery — Slug Registration

`CharakaParser.__init__()` calls `self.hierarchy.pre_scan()` which:

0. **Administrative Filtering**: Skips 12+ administrative/meta files (e.g., `Donate.json`, `Guidelines for writing.json`, `Main Page.json`).
1. Reads `*Abstracts*` JSON files to build `toc_map` — maps normalized page titles to sthana IDs.
2. Reads ALL JSON files to build `affinity_map` using link-affinity scoring:
   - **Admin keywords** (`Contributors`, `Project`, `Guidelines`, etc.) → mapped to `meta_hub_id`.
   - **Glossary keywords** (`List_of_herbs`, `Botanical`, `Glossary`) → mapped to `materia_medica_id`.
   - **Direct ToC match** → assigned to the sthana from Abstracts.
   - **Link-affinity scoring**: For remaining pages, counts outgoing links pointing to sthana pages (weight 10) or to pages in the ToC (weight 2). Highest-score sthana wins.
   - **Default fallback**: If no links match, assigned to `root_id`.

Then `main.py::main()` calls `registry.register(data["title"], data["url"])` for every JSON file, building `SlugRegistry.title_to_id` and `SlugRegistry.slug_to_id`.

### Pass 2: Indexing — Document Classification and Chunking

`CharakaParser.parse(data)` classifies each document and dispatches to the appropriate parser:

#### Document Classification (`classify_document`)

| Condition | Type |
|-----------|------|
| Text starts with "Preamble of" + "Contents" OR title contains "Abstracts -" | `TYPE_STHANA` (`"sthana_index"`) |
| Text > 40000 chars AND has Devanagari | `TYPE_CHAPTER` (`"chapter_root"`) |
| Has "Herb database" in HTML OR matches `^[A-Z][a-z]+ [a-z]+` pattern, length < 10000 | `TYPE_BOTANICAL` (`"stub_botanical"`) |
| Has "Panchakarma" in HTML OR "purvakarma"+"pradhanakarma" in text | `TYPE_PROCEDURAL` (`"procedural_article"`) |
| "Contents" in text AND length > 5000 | `TYPE_CONCEPT` (`"concept_article"`) |
| Text length < 500 | `TYPE_GLOSSARY` (`"stub_glossary"`) |
| Default fallback | `TYPE_CONCEPT` |

#### Chunking Strategies

**Botanical entries** (`parse_botanical`):
- Single chunk per document.
- Strips the "Contents\n..." section and everything after "Send us your suggestions".

**Glossary entries** (`parse_glossary`):
- Single chunk per document with the full text.

**Sthana index pages** (`parse_sthana`):
- Single chunk per document, parent = treatise root.

**Articles (Concept and Procedural)** (`parse_article`):
- Looks for a `Contents\n\n...\n\n` section to extract a table of contents.
- If ToC found with section titles: creates a **lede chunk** (content before first section) as the article root, then creates **section chunks** by splitting at each section title boundary.
- Section titles extracted via regex `^\d+(\.\d+)*\s+` prefix stripping.
- Each section chunk has `TYPE_SECTION` with `section_title` and `anchor` metadata.
- If no ToC found: single chunk.

**Chapter pages** (`parse_chapter`):
- Creates a **chapter root chunk** with either the Abstract content (between "Abstract\n\n" and "\n\nKeywords") or a placeholder.
- Extracts **verse chunks** using regex `([\u0900-\u097F]{10,}.*?\[(\d+[-–\d,\s]*)\](.*?))(?=\n\n[\u0900-\u097F]|$)`.
- **Bilingual Pairing**: The regex now captures the subsequent English translation block immediately following the Sanskrit shloka to prevent fragmentation.
- Each verse chunk has `TYPE_VERSE` with metadata: `verse_ref`, `sanskrit_count`, `is_tripartite`, and `linguistic_type: "bilingual"`.

### Chunk Metadata Fields

Every chunk dict contains:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | UUID v5: `generate_id(f"{cid}_{clevel}_{title}_{content_hash}")` where content_hash is first 100 chars of content |
| `canonical_id` | str | From `SlugRegistry.register()` — canonicalized title |
| `parent_id` | str | Sthana ID from affinity map, or treatise_root_id, or chapter/article root |
| `prev_id` | str or None | Set during linking pass |
| `next_id` | str or None | Set during linking pass |
| `level` | str | One of the TYPE_ constants |
| `title` | str | Document title or section title |
| `content` | str | Extracted text content |
| `url` | str | Original wiki URL |
| `metadata` | dict | Type-specific metadata (section_title, anchor, verse_ref, etc.) |

### Linked List Construction

After each `parse()` call, chunks within a document are linked: `chunks[i]["next_id"] = chunks[i+1]["id"]` and reverse for prev.

## Artifact Generation

The Charaka worker (`src/chunking/charak_samhita_chunking/main.py`) performs a two-pass process:
1. **Pre-scan**: Registers all 641 JSON slugs to ensure cross-document links can be resolved.
2. **Parsing**: Processes every file and accumulates all chunks.

Outputs to `processed-books/charak_samhita/`:
- **`canonical.md`**: A sequential Markdown file containing all chunks in the order they were parsed. Useful for human review.
- **`vectors.jsonl`**: The raw chunk data used as input for Phase 4 (Cross-Linking) and Phase 5 (Uploading).

## Named Vectors Produced

Per chunk in `AyurvedaDatabaseManager.upload_chunks()`:
- **`dense_english`**: `RemoteEmbedder.encode("passage: " + title + content)` — 1024-dim float vector, COSINE distance.
- **`dense_sanskrit`**: `RemoteEmbedder.encode("passage: " + _normalize_sanskrit(title + content))` — same dim/distance. The normalization combines Devanagari and IAST representations.
- **`sparse_splade`**: `RemoteEmbedder.encode_sparse(title + content)` — sparse vector via SPLADE-v3 model.

## Edge Cases and Malformed Chunks

- **Empty or minimal text** (< 500 chars): classified as `TYPE_GLOSSARY`.
- **No Devanagari in long text**: NOT classified as `TYPE_CHAPTER`, falls to `TYPE_CONCEPT`.
- **Missing Abstract section** in chapter: chapter root gets `f"Chapter: {title}"` as content.
- **No ToC sections** in article: single chunk with full text.
- **Redlink URLs** (containing `redlink=1` or `action=edit`): `SlugRegistry.resolve()` returns None; these are ignored during link resolution.
- **Outgoing links to non-existent files**: `pre_scan()` silently catches exceptions via `except: continue`.
- **Multi-byte verse references**: `[11-14]` ranges are captured and passed through.

## Link-Affinity Reconstruction Details

The `CharakaHierarchyManager.pre_scan()` method implements a graph-based approach:

1. **Abstracts files** (e.g., "Abstracts - Sutra Sthana.json") contain the table of contents for one sthana. Every link in an Abstracts file is mapped to that sthana's ID in `toc_map`.
2. For non-Abstracts files, the algorithm counts weighted link scores:
   - Direct link to a sthana page (e.g., outgoing link mentioning "Sutra Sthana"): weight +10
   - Link to a page known to be in the ToC: weight +2
3. The sthana with the highest score wins. Ties broken by `max(scores, key=scores.get)` (first max).
4. If no sthana scores > 0, the page is assigned to `root_id`.
