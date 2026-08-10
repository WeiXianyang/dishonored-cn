# Generic review and release contracts

## Normalized record

```json
{
  "id": "release|resource|object|field|occurrence",
  "source": "source-language text",
  "baseline": "existing translation",
  "domain": "base|dlc|mod|build",
  "content_type": "ui|subtitle|objective|item|note|system",
  "locale": "target-locale",
  "relationships": [],
  "provenance": {
    "resource": "relative/path",
    "object": "section or object path",
    "field": "key or property",
    "occurrence": 0,
    "speaker": "",
    "neighbors": [],
    "branch": "",
    "audio_event": "",
    "cue": {"id": "", "start_ms": null, "end_ms": null}
  },
  "format": {
    "encoding": "UTF-8",
    "newlines": "LF",
    "placeholders": [],
    "interpolation": [],
    "tags": [],
    "markup_signature": "",
    "plural_select_signature": "",
    "layout": {"max_lines": null, "max_width": null, "max_cps": null}
  },
  "hashes": {
    "source": "sha256:...",
    "baseline": "sha256:..."
  }
}
```

Extend this schema for a format, but do not remove frozen provenance or invariants.

## Proposal

```json
{
  "id": "stable-id",
  "action": "keep|propose_change|research_required",
  "candidate": "",
  "evidence_basis": "source|baseline|runtime",
  "error_type": "mistranslation|omission|entity|relation|number|negation|modality|typo|format|other",
  "source_span": "exact source phrase",
  "baseline_span": "exact target phrase",
  "baseline_problem": "specific demonstrable defect",
  "target_delta": "smallest necessary change",
  "uncertainty_question": "",
  "confidence": 0.0
}
```

For `keep`, require `candidate` to be empty. For `propose_change`, require `candidate != baseline` and a hard-error explanation. Semantic changes require an exact source span; target-only mechanical repairs may instead cite an exact baseline span or reproducible runtime evidence. Validate placeholders, interpolation, plural/select branches, tags, timing, and layout outside the model through adapter rules.

## Critic decision

```json
{
  "id": "stable-id",
  "decision": "accept_candidate|revert_baseline|research_required",
  "reason": {
    "error_type": "mistranslation",
    "source_span": "exact source phrase",
    "baseline_problem": "specific defect",
    "candidate_scope": "why every target change is necessary"
  },
  "confidence": 0.0,
  "research_question": ""
}
```

Do not include replacement text. Merge code owns the candidate and frozen baseline. Unknown decisions and third wording are fatal validation errors.

## Evidence record

```json
{
  "id": "stable-id",
  "question": "one falsifiable question",
  "status": "direct_evidence|context_only|conflict|no_match",
  "finding": "fact supported by the source, without a translation leap",
  "sources": [
    {
      "title": "source title",
      "url": "direct URL or local artifact path",
      "excerpt": "short supporting excerpt",
      "authority": "local|official|wiki|gameplay|lexical",
      "accessed_at": "ISO-8601"
    }
  ],
  "inference": "how the evidence affects this record"
}
```

## Deterministic merge rules

1. Start from a fresh copy of the frozen baseline.
2. Require exactly one decision for every proposal ID.
3. Apply the stored candidate only for `accept_candidate`.
4. Use the full frozen baseline for `revert_baseline` and `research_required`.
5. Reject unknown, missing, duplicate, or conflicting IDs.
6. Recompute invariants and scoped terminology.
7. Re-extract output and compare stable-ID coverage.
8. Emit accepted, reverted, unresolved, exception, and effective-change ledgers.

## Release manifest minimum

Record project/build/languages, frozen input hashes, adapter and configuration fingerprints, corpus counts, accepted/reverted/unresolved counts, invariant results, runtime test scope, artifact hashes, installation steps, rollback steps, and known limitations.

## Minimal regression set

Include at least one gold case and one mutation for each applicable family:

- placeholder, tag, escape, newline, or encoding damage;
- negation, modality, number, comparison, sequence, or direction change;
- actor/patient, speaker/listener, pronoun, or relationship swap;
- named entity, title, object type, interaction, or cross-release collision;
- short term corrupting a longer compound;
- fluent rewriting that adds an unsupported fact;
- duplicate visible strings with distinct runtime identities.

Critical mutations must be rejected at 100% before release.
