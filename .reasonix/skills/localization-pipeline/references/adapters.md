# Format-adapter guide

## Adapter boundary

Keep container parsing and byte-preservation code outside semantic review. A format adapter should expose a small deterministic interface:

```text
discover(scope) -> resources
extract(resource, language) -> records
identify(record) -> stable_id
render(staging_tree, accepted_changes) -> rendered_tree
verify(rendered_tree, frozen_manifest) -> report
package(rendered_tree, release_config) -> artifacts
```

The semantic pipeline should consume normalized records and return decisions keyed by stable ID. It should not know whether text came from a spreadsheet, database, engine object, or archive.

## Stable identity

Build IDs from structural provenance, such as:

```text
release | relative_resource | object/section | field/key | occurrence | variant
```

Prefer engine-native identity when available: table/key GUIDs, asset GUID plus local object ID, translation-block IDs, database primary keys, dialogue-node IDs, or archive object paths. Add occurrence and branch information only as needed. Treat line numbers, array positions, generated hashes, and source hashes as drift detectors or build-scoped fallbacks, never as the sole identity. Detect ID drift after game updates.

Create explicit alias or relationship records when multiple resources intentionally represent one logical string. Never synchronize changes across resources merely because visible text is equal.

## Common format families

### Flat tables and interchange formats

CSV/TSV, PO, XLIFF, JSON, YAML, XML, INI, properties, and vendor string tables may carry IDs directly. Preserve column order, comments, quoting, plural/select branches, locale fallback, escape rules, and duplicate keys. Validate named variables, conversions, nested formatting, fonts/glyph coverage, and smart-string behavior through format-specific rules. Do not round-trip through a serializer that rewrites unrelated bytes unless that is explicitly accepted.

### Databases

For SQLite or custom stores, record table, primary key, column, locale, and row-version provenance. Write inside a transaction in a copy. Verify schema, indexes, row counts, constraints, and unaffected columns after rendering.

### Engine assets and archives

For Unreal, Unity, Ren'Py, RPG Maker, or custom engines, use a tested extractor/repacker for the exact game build. Preserve object paths, package indexes, compression/alignment rules, checksums, signatures, and fonts. Treat an extracted text file as an intermediate representation; successful text editing does not prove successful repacking.

For Unity Addressables, distinguish a project rebuild from direct published-bundle modification. Validate catalog and hash files, bundle CRCs, dependencies, address/key mappings, compression, locale fallback, fonts, and the target platform.

For Ren'Py, use syntax-aware parsing rather than regex or global replacement. Separate dialogue, menu, and translation nodes from Python, screen language, labels, comments, and character definitions. Preserve labels and translation-block IDs; validate interpolation conversions, text tags, escaped brackets/braces, and route-specific behavior. Distinguish editable `.rpy` from compiled `.rpyc` and packed `.rpa`, and run the matching SDK's lint/compile checks when available.

### Subtitles and dialogue graphs

Preserve locale, track, cue/event ID, start/end/duration, speaker, listener, trigger, timeline, audio event, branch/call path, neighboring lines, line count, reading speed, and width limits when available. Sequence position alone is fragile when optional branches or repeated barks exist.

## Required round-trip tests

Before semantic work, prove:

1. zero-change extraction and rendering preserves semantics and, where possible, bytes;
2. one synthetic edit lands on exactly one intended occurrence;
3. duplicate visible strings remain distinguishable;
4. adapter-defined placeholders, interpolation, plural/select branches, markup, escapes, newlines, timing, layout constraints, and encoding survive;
5. re-extraction returns the same stable IDs;
6. packaging installs and rollback restores the frozen baseline.

If a zero-change build is not byte-stable, document deterministic expected differences and verify that no semantic or structural content drifts.

## Adapter stop conditions

Stop before review or release when resource coverage is unknown, IDs change between runs, a serializer rewrites unrelated content, repacking is not reproducible, or runtime loading cannot be verified.
