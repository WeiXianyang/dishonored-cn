---
name: localization-pipeline
description: Audit, repair, validate, and release an existing game localization without turning the work into a rewrite. Use for bilingual corpus alignment, translation-patch repair, terminology control, subtitle or UI review, AI-assisted QA, adversarial second review, deterministic writeback, changelogs, and release validation across any engine or text format.
---

# Repair Existing Game Localizations Safely

Preserve the shipped or community translation as a protected baseline. Change only demonstrable defects, keep every accepted edit traceable to frozen inputs, and make rollback possible.

## Establish the project contract

Before editing anything, collect:

- game, build, platform, language pair, base game/DLC/mod scope;
- source-language material and the exact baseline translation;
- archive, database, engine, encoding, newline, placeholder, markup, and packaging constraints;
- permission or redistribution constraints;
- available runtime evidence: scripts, object paths, screenshots, audio, dialogue trees, or reproducible saves;
- success criteria, installation path, rollback path, and release artifact shape.

Ask for missing inputs that would change extraction, identity, or packaging. If source text is unavailable, limit work to mechanical and monolingual defects; do not claim semantic correctness.

Freeze hashes of every input before extraction. Never edit the only copy of a game file.

## Separate the invariant workflow from format adapters

Keep the review pipeline format-independent. Put engine and file knowledge behind an adapter with these operations:

1. `discover` — enumerate all in-scope resources and releases;
2. `extract` — emit source and baseline text plus provenance;
3. `identify` — assign stable IDs from structure, never text alone;
4. `render` — write an allowlisted set of accepted changes into staging;
5. `verify` — re-extract and check structure, encoding, placeholders, and coverage;
6. `package` — produce installable and reversible artifacts.

Use this workflow for CSV/TSV, PO/XLIFF, JSON/YAML/XML, INI/properties, string tables, SQLite or custom databases, subtitle resources, and extracted engine archives. Do not assume direct support for a container merely because its extracted text is supported. Read [references/adapters.md](references/adapters.md) before implementing or changing an adapter.

## Use one stable record contract

Normalize every translatable occurrence to a record containing:

- stable ID and any explicit alias/relationship to other records;
- source text and frozen baseline translation;
- release/domain and content type;
- resource path, section/object/field, occurrence, and dialogue or scene provenance;
- neighboring context when available;
- encoding, newline, placeholder, interpolation, tag, markup, plural/select, layout, and timing signatures when applicable;
- source and baseline hashes.

Preserve duplicate strings when their objects or runtime contexts differ. Keep missing translations distinct from deliberately empty overrides. Record unmatched rows instead of silently dropping them.

Read [references/contracts.md](references/contracts.md) when creating schemas, prompts, validators, or a merge gate.

## Run the eight-stage repair pipeline

### Phase 0 — Intake and freeze

Define scope, rights, versions, adapters, invariants, evaluation samples, and rollback. Hash inputs and create an isolated staging tree.

### Phase 1 — Extract and align

Extract both language sides, align by structural identity, measure coverage, and investigate every duplicate, missing, or unmatched ID. Make the aligned corpus the only semantic-review input.

### Phase 2 — Build scoped terminology

Mine candidate entities and repeated phrases, then classify each as:

- globally stable;
- exact-case only;
- label/item-name only;
- context, speaker, release, or DLC specific;
- rejected or ambiguous.

Use longest-match and boundary checks, but never treat string matching as proof. Any edit introduced by a term match still requires semantic review.

### Phase 3 — Propose minimal repairs

Have the proposer compare source, baseline, and context. `keep` is the default. Permit changes only for hard defects such as mistranslation, omission, wrong entity, reversed relation, broken number/negation/modality, typo, corrupted placeholder, or clearly defective machine output.

Reject preference-only rewrites, tone modernization, synonym swaps, and fluency polishing when the baseline meaning is already sound.

Each proposal must identify its evidence basis, the exact supporting source or baseline span, baseline defect, minimal target delta, evidence or uncertainty, and affected format signature. Require a source span for semantic changes; allow a baseline or runtime span for target-only mechanical defects. Use structured output and validate ID coverage deterministically.

### Phase 4 — Research and human adjudication

Route insufficient-context cases to a queue. Ask one falsifiable question per case. Prefer exact-build local evidence, then scripts/object bindings/audio/captures, then official material or reputable community references. A search hit is not proof; no hit is not disproof.

Keep raw evidence separate from the translation decision. If no external reference exists, use reproducible local control flow, audio, captures, and saves; if those do not settle the question, retain `research_required` and release the frozen baseline. If both baseline and candidate are wrong, create a new proposal and restart review instead of editing inside the adjudication step.

### Phase 5 — Run an adversarial second review

Hide the proposer rationale and confidence. The critic may return only:

- `accept_candidate`;
- `revert_baseline`;
- `research_required`.

Forbid third wording. An accepted candidate must be supported by a hard baseline defect; equal meaning is a reason to revert. Review all semantic changes, prioritizing altered placeholders, numbers, negation, modality, direction, participants, entities, interactions, and large rewrites.

### Phase 6 — Merge, render, and package deterministically

Treat accepted stable IDs as an allowlist. Revert unresolved cases to the frozen baseline. Reject unknown, duplicate, missing, or conflicting IDs. Recompute placeholder, tag, terminology, and structural checks from source data rather than trusting model flags.

Render only into staging. Preserve byte-level properties where the format requires them. Re-extract the rendered output, create an effective changelog with `old != new`, and package with hashes, install instructions, and rollback instructions.

### Phase 7 — Validate and release

Run static checks on full coverage, structure, encoding, placeholders, tags, line breaks, file inventory, deterministic rebuilds, and expected diffs. Then smoke-test representative runtime paths for base game and every scoped expansion: menus, objectives, subtitles, notes, item names, prompts, choices, fonts, and fallback behavior.

Publish only verified artifacts, a manifest, a changelog, unresolved/exception ledgers, and known limitations. When redistribution rights are limited, publish a legal delta/patch and installer instead of full extracted scripts or assets.

## Enforce release gates

Reject release if any accepted edit lacks frozen provenance, stable identity, independent review, a closed decision, invariant validation, or resolved evidence when facts were required.

Also reject:

- missing or duplicate IDs;
- critic-authored third translations;
- changed placeholders, tags, keys, or structure outside an approved adapter rule;
- unexplained divergence for exact-source duplicates;
- packaging changes that cannot be installed and rolled back reproducibly;
- critical regression cases that are not detected at 100%.

Turn every discovered failure into a gold regression case plus at least one mutation. Include negation, modality, number, direction, actor/patient swaps, pronouns, entity collisions, compound-term pollution, unsupported added facts, and runtime-marker damage.

## Scale without weakening coverage

Batch by both record count and serialized context size. Group by resource, scene, dialogue, or object when that preserves meaning. Save each batch independently, fingerprint prompts/configuration/model/adapters, support resume, and invalidate caches when any fingerprint changes.

Use risk scores only to order work, never to approve changes or skip review. Pause and recalibrate when modification, uncertainty, overturn, invariant-failure, or unsupported-evidence rates spike.

## Produce reusable outputs

Keep these artifacts even when filenames differ by project:

- frozen input manifest and aligned corpus;
- scoped glossary and rejected-term ledger;
- proposals, critic decisions, research queue, and evidence records;
- accepted allowlist, reverted/unresolved/exception ledgers;
- regression and mutation corpus;
- rendered patch, effective changelog, release manifest, hashes, install and rollback guide.

For a compact implementation checklist and generic data examples, use [references/contracts.md](references/contracts.md). Treat this repository's Dishonored implementation as a case study, not as a mandatory engine or tool choice.
