# Susruta Samhita Chunking

## Raw Input Format

The parser receives a single Markdown file at `books/shusrut_samhita/Shusrut_Samhita.md`.

The file is an OCR-derived Markdown document with this structure:

```markdown
---
... metadata ...
---

INTRODUCTION
...introductory text...

## S.S. II. 1
(SS reference citation markers)

CHAPTER ONE NIDÃNA-STHANA
...chapter header...

## SUMMARY
...summary text...

## 1. Section Title Here
...section content...

## 2. Next Section Title
...section content...

## 16, 17/1. Verse-style heading
...content with footnotes...

SUGGESTED RESEARCH PROBLEMS
...apparatus section...

Chapter Two NIDANA STHANA
...
```

## Parsing Structure — State Machine

`parse_shusrut_samhita(file_path)` uses a **finite state machine** with `ParserState` enum:

```
States:
  FRONTMATTER ──> CHAPTER_HEADER ──> CHAPTER_PREAMBLE ──> CHAPTER_BODY ──> APPARATUS
```

### State Transitions

1. **FRONTMATTER**: Collects all lines until a `CHAPTER` header is detected. The `intro_buffer` accumulates introductory text.

2. **CHAPTER_HEADER** → **CHAPTER_PREAMBLE**: Triggered when a line matches `CHAPTER [WORD] NIDÃNA-STHANA` or `CHAPTER [WORD] NIDANA STHANA`.
   - **Image Metadata Extraction**: If `base64` image strings are detected, their surrounding captions/alt-text are extracted into chapter metadata before stripping.
   - **Keyword Preservation**: Keywords from the "SUGGESTED RESEARCH PROBLEMS" section are extracted and tagged to the chapter as `research_keywords` for query expansion.
   - The chapter number is extracted from the word (e.g., "One"→1, "Two"→2, etc. via `num_map`) or digits. `"THUS ENDS"` lines are skipped. State becomes `CHAPTER_HEADER`, then immediately checks for transitions.

3. **CHAPTER_PREAMBLE**: Triggered by `## SUMMARY`. Lines are collected in `summary_buffer`. Transition to `CHAPTER_BODY` occurs when a section heading or `## Chapter` line is detected.

4. **CHAPTER_BODY**: Collects section content. Section boundaries are detected by `is_section_heading(line)` which matches:
   - Lines starting with `##` (excluding metadata markers like "Indological Truths" or citation markers)
   - Lines starting with a verse number pattern: `^\d+([\s,/-]+\d+([/\.]\d+)?)?[\.\s]+[A-Z]`

5. **APPARATUS**: Triggered by `SUGGESTED RESEARCH PROBLEMS`. Content is ignored (skipped).

### `is_section_heading` Detection

```python
# Matches patterns like:
# "## 14/2, 15. Udana Vayu"
# "16, 17/1. Samãna Vãyu"
# "## 26-29 Effects of..."
# "## Some Title"  (but NOT metadata-only markers)
```

## Chunk Types Produced

| Level | Description | Parent |
|-------|-------------|--------|
| `"book"` | Treatise root | None |
| `"sthana_index"` | Nidana Sthana node | treatise root |
| `"section"` | Introduction text | sthana |
| `"chapter"` | Chapter node (summary) | sthana |
| `"section"` | Section content blocks | chapter |
| `"stub_glossary"` | Virtual glossary stubs | chapter |

### Chapter Chunks

Created when transitioning from PREAMBLE to BODY. Content is the SUMMARY text (cleaned) or a fallback `"Chapter {N}: {title}"`. Each chapter gets metadata:
- `chapter_number`: int (1-16)
- `chapter_title`: from `get_chapter_title_from_intro()` mapping (e.g., "Diagnosis of Vatika Diseases")
- `ss_reference`: citation marker like "S.S.II.1"

### Section Chunks

Created by `flush_sections()` when a section boundary is hit. A section chunk contains:

| Field | Source |
|-------|--------|
| `id` | UUID v5: `f"ss_{chapter_num}_{title}_{i}_{content_hash}"` |
| `level` | `"section"` |
| `parent_id` | current chapter ID |
| `content` | Cleaned text (HTML entities decoded) |
| `metadata.chapter_number` | int |
| `metadata.chapter_title` | str |
| `metadata.section_title` | Extracted from heading via `extract_verse_info()` |
| `metadata.derived_title` | bool — True if title was inferred from first sentence |
| `metadata.verse_start` | float or None |
| `metadata.verse_end` | float or None |
| `metadata.has_footnotes` | bool — true if content contains numbered footnotes (`\n\d+\.\s`) |
| `metadata.word_count` | int |

### Verse Info Extraction

`extract_verse_info(heading)` parses headings like:
- `"## 14/2, 15. Udana Vayu"` → start=14.2, end=15.0, title="Udana Vayu"
- `"16, 17/1. Samãna Vãyu"` → start=16.0, end=17.1, title="Samãna Vãyu"
- `"## 26-29 Effects of..."` → start=26.0, end=29.0, title="Effects of..."
- `"## 11."` → start=11.0, end=11.0, title="" → falls to derived title logic

### Long Section Splitting

If a section exceeds 500 words (`max_words`), `split_long_section()` splits it at paragraph boundaries (`\n\n`) such that each part is ≤ 500 words. Multi-part sections get a suffix (`_part1`, `_part2`) in the section_title metadata.

### Virtual Glossary (Header Promotion)

For each section whose heading title is NOT derived (i.e., has a real verse-numbered title) AND length > 3 chars, a **glossary stub** chunk is created:

```python
{
    "id": generate_stable_id(f"glossary_ss_{chapter_num}_{title}"),
    "level": "stub_glossary",
    "parent_id": chapter_id,
    "content": f"Topic: {title}. Surgical/Pathological entry in Susruta Samhita, Chapter {chapter_num}.",
    "metadata": {"title": title, "source": "shusrut_samhita", "context": "promoted_header"}
}
```

This ensures that surgical/procedure headers serve as search anchors, eliminating Charaka-only glossary bias.

### Orphan Heading Handling

If a heading like `## 12.` has no title text (empty after `extract_verse_info`), the first sentence of the body text (< 100 chars) is used as the derived title. `derived_title` is set to `True` and no glossary stub is generated.

## Sequential Edge Linking

`link_sequential_edges()` traverses all chunks and sets `prev_id` / `next_id` for consecutive sections WITHIN the same chapter (by `chapter_number`). Cross-chapter linking is NOT done.

## Artifact Generation

The Susruta worker (`src/chunking/shusrut_samhita_chunking/main.py`) processes the single source Markdown file and outputs results to `processed-books/shusrut_samhita/`:

- **`canonical.md`**: A sequential Markdown file where each heading corresponds to a chunk title.
- **`vectors.jsonl`**: The source of truth for the vector database, containing all metadata and hierarchy fields.

## Named Vectors Produced


- **Base64 images** in markdown: lines containing `data:image/png;base64,` are filtered out.
- **Indological Truths marker**: `## Indological Truths` lines are excluded.
- **Citation markers**: `## S.S. II. N` lines are captured for `ss_reference` metadata but excluded from content.
- **`---` and `--` lines**: filtered globally.
- **Unknown chapter numbers**: If the word-to-number mapping fails, the previous chapter number persists.
- **Duplicate chapter IDs**: Checked before appending to avoid duplicates.
- **Empty section buffers**: `flush_sections` returns early if buffer is empty.
- **Unicode normalization**: `clean_text` uses `html.unescape()` to decode HTML entities.

## Named Vectors Produced

Same as Charaka (`AyurvedaDatabaseManager.upload_chunks()`):
- `dense_english`: E5 embedding of `"passage: " + title + content`
- `dense_sanskrit`: E5 embedding of `"passage: " + _normalize_sanskrit(title + content)`
- `sparse_splade`: SPLADE sparse vector of `title + content`

## Current Coverage

The parser is designed for **Nidana Sthana only** (16 chapters on etiology). `sthana_id` is hardcoded to `generate_stable_id("sthana_nidana_susruta")`. The `get_chapter_title_from_intro()` mapping covers exactly chapters 1-16. Other Sthanas of Susruta Samhita are not covered.
