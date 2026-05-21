# Astanga Hridayam Chunking

## Raw Input Format

The parser receives a single Markdown file at `books/astanga_hridaya/astanga-hridaya.md`.

The file is structured as a Markdown document with `##` headings:

```markdown
## Chapter 1: Title of Chapter

...some content...

## Section Heading in English

...content with Devanagari shlokas...

## श्लोकः (Devanagari shloka heading - NOT a section boundary)

...more content...

## Next English Section

...content...

## Astanga Hridaya Sutrasthan
(skip this line)
```

## Parsing Structure — Line-by-Line Tree Traversal

`parse_astanga_hridaya(file_path)` processes the file **line by line** with no explicit state machine. The algorithm:

### Global Hierarchy (Created First)

1. **Treatise Root**: `id = generate_stable_id("root_astanga_hridaya")`, level `"book"`, parent=None
2. **Sthana Node**: `id = generate_stable_id("sthana_sutra_astanga")`, level `"sthana_index"`, parent=treatise root

### Line Processing Rules

**Rule 1 — Chapter Boundary**:
Regex: `r'^## Chapter (\d+)[ :]*(.*)'`
When matched:
- Flush current section buffer (if any) as a section chunk.
- Set `current_chapter_num` from capture group 1 (integer).
- Set `current_chapter_title` from capture group 2.
- Create chapter chunk: `id = generate_stable_id(f"ch_{num}_{title}")`, level `"chapter"`, parent=sthana.
- Start a "Chapter Introduction" section immediately: `id = generate_stable_id(f"ch_{num}_intro")`, title = "Chapter Introduction".

**Rule 2 — Devanagari Headings are NOT Section Boundaries**:
If a `##` heading is Devanagari (detected by `is_devanagari()` with threshold > 0.4 ratio), the line is appended to the current section buffer. Devanagari headings are treated as shloka content, not structural boundaries.

**Rule 3 — English Section Headings**:
If a `##` heading is NOT Devanagari (i.e., Roman/Latin script):
- Flush the current section buffer.
- Start a new section with `id = generate_stable_id(f"ch_{num}_{title}")`.
- Generate a **virtual glossary stub** (see below).

**Rule 5 — Anomaly**:
`## Astanga Hridaya Sutrasthan` is explicitly ignored (continue without processing).

**Default**:
All other lines are appended to `current_section_buffer`.

### Section Chunk Structure

Created by `create_section_chunk()`:

| Field | Source |
|-------|--------|
| `id` | `generate_stable_id(f"ch_{ch_num}_{sec_title}")` |
| `level` | `"section"` |
| `parent_id` | current chapter ID |
| `prev_id` | previous section ID in same chapter |
| `next_id` | None (set later) |
| `content` | Cleaned: `\n`.join(buffer), strip ``` fences, `html.unescape()` |
| `metadata.chapter_number` | int |
| `metadata.chapter_title` | str |
| `metadata.section_title` | str |
| `metadata.verse_start` | float or None — extracted from section title via `extract_verse_numbers()` |
| `metadata.verse_end` | float or None |
| `metadata.has_sanskrit` | bool — `is_devanagari(content)` |
| `metadata.word_count` | int |

### Virtual Glossary (Header Promotion)

For every English section heading, a glossary stub is created:

```python
{
    "id": generate_stable_id(f"glossary_astanga_{title_candidate}"),
    "level": "stub_glossary",
    "parent_id": current_section_id,
    "content": f"Topic: {title_candidate}. Found in Astanga Hridaya, Chapter {current_chapter_num}.",
    "metadata": {"title": title_candidate, "source": "astanga_hridaya", "context": "promoted_header"}
}
```

This follows the same bias-elimination strategy as Susruta's header promotion.

### Sequential Edge Linking

After all lines are processed and the final section is flushed, the parser does a second pass:
- For each `section`-level chunk, find the next `section` chunk WITHIN the same chapter (by `chapter_number`).
- Set `chunks[i]["next_id"]` and `chunks[j]["prev_id"]`.

Note: The chapter intro section (created at chapter boundary) is included in this sequential chain.

## Unique Behavioral Points

### Verse-Commentary Pair Preservation

Astanga's approach to keeping verse-commentary pairs together is implicit: Devanagari headings (`## श्लोकः`) are NOT treated as section boundaries (Rule 2). This means a Devanagari shloka heading and the following commentary remain in the same buffer as the preceding English section. The entire block becomes one section chunk.

### Structural Differences from Charaka and Susruta

| Aspect | Charaka | Susruta | Astanga |
|--------|---------|---------|---------|
| Source format | Individual JSON files | Single Markdown file | Single Markdown file |
| Parsing strategy | Link-affinity + document classification | State machine (5 states) | Line-by-line boundary detection |
| Chapter detection | Via document classification | Via `CHAPTER [WORD]` regex | Via `## Chapter [N]` regex |
| Section detection | Via ToC splitting | Via `is_section_heading()` | Via Devanagari-filtered `##` |
| Glossary stubs | Only from existing glossary entries | Promoted from all section headers | Promoted from all English section headers |
| Hierarchy | 8 Sthanas + Meta + Materia Medica | 1 Sthana (Nidana) | 1 Sthana (Sutra) |
| ID namespace | `root_charaka_samhita` | `root_susruta_samhita` | `root_astanga_hridaya` |

### Malformed Chunk Handling

- **Empty sections**: If a section has only the heading line, `clean_content()` returns an empty string. The chunk is still created.
- **Code fences in content**: Triple backticks (```) are stripped from content.
- **HTML entities**: `html.unescape()` decodes all entities (e.g., `&amp;` → `&`, `&lt;` → `<`).
- **Non-Devnagari `##` headings with special characters**: Any `##` line that fails `is_devanagari()` is treated as a section boundary, even if it contains punctuation or numbers.
- **Missing chapter intro section**: Always created at chapter boundary, even if no content follows immediately.

### Current Coverage

The parser is designed for **Sutra Sthana** only. The sthana ID is hardcoded to `generate_stable_id("sthana_sutra_astanga")`. Other Sthanas of Astanga Hridayam are not covered in the current parser.

## Named Vectors Produced

Same as Charaka/Susruta (`AyurvedaDatabaseManager.upload_chunks()`):
- `dense_english`: E5 embedding of `"passage: " + title + content`
- `dense_sanskrit`: E5 embedding of `"passage: " + _normalize_sanskrit(title + content)`
- `sparse_splade`: SPLADE sparse vector of `title + content`
