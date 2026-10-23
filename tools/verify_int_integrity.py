"""Release regression gate for all Dishonored INT entries and format tokens."""
from __future__ import annotations
import argparse, hashlib, json, re, zipfile
from pathlib import Path
from int_schema import decode_int_bytes, parse_int_text

INT_SUFFIX = ".int"
TOKEN_PATTERNS = {
    "backtick": re.compile(r"`([^`]*)`"),
    "GBA": re.compile(r"(?i)\bGBA_[A-Za-z0-9_]+\b"),
    "KEY": re.compile(r"(?i)\bKEY_[A-Za-z0-9_]+\b"),
    "dollar": re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$"),
    "printf": re.compile(r"%(?:\d+\$)?[-+#0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlLzjt]*[diuoxXfFeEgGaAcspn%]"),
    "brace": re.compile(r"\{[A-Za-z_][A-Za-z0-9_.:-]*\}"),
    "tag": re.compile(r"</?[A-Za-z][^<>]*?>"),
    "escape": re.compile(r"\\[rnt]"),
    "unresolved": re.compile(r"\?INT\?|\+{3,}"),
}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def analyze_int(data: bytes, expected_struct_fields: set[str] | None = None) -> dict:
    if not data:
        return {"encoding": "empty", "entry_count": 0, "schema_sha256": sha(b"[]"), "duplicates": {"section_blocks": [], "assignment_names": [], "struct_leaf_names": []}, "entries": [], "issues": []}
    text, encoding = decode_int_bytes(data)
    # The byte decoder consumes one byte-order mark. Preserve and diagnose any
    # further U+FEFF instead of lstrip() silently normalizing the defect.
    issues = []
    if "\ufeff" in text:
        issues.append("embedded_or_duplicate_bom")
    parseable_text = text[1:] if text.startswith("\ufeff") else text
    lines = parseable_text.splitlines()
    section = ""
    assignment_occurrences = {}
    parsed = parse_int_text(parseable_text, "fixture.int")
    entries = []
    sections = []
    assignments = []
    logical_fields = []
    for entry in parsed:
        value = entry["value"]
        tokens = {name: pattern.findall(value) for name, pattern in TOKEN_PATTERNS.items()}
        residue = TOKEN_PATTERNS["tag"].sub("", value)
        tokens["malformed_angle"] = "<" in residue or ">" in residue
        entries.append([
            entry["section"], entry["key"], entry["assignment_occurrence"],
            entry["subkey"], entry["field_occurrence"], tokens,
        ])
        assignments.append((entry["section"], entry["key"]))
        logical_fields.append((entry["section"], entry["key"], entry["assignment_occurrence"], entry["subkey"]))
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("["):
            if not stripped.endswith("]"):
                issues.append(f"malformed_section:{number}")
            else:
                section = stripped[1:-1].strip()
                sections.append(section)
            continue
        if not stripped or stripped.startswith((";", "#", "//")):
            continue
        if "=" not in stripped:
            issues.append(f"missing_equals:{number}")
        elif expected_struct_fields:
            # Only source-confirmed string leaves are checked. Numeric, boolean,
            # enum, and object-reference scalar values remain valid unquoted.
            assignment = re.match(r"^\s*([^\s=]+)\s*=\s*(.*)$", line)
            if assignment and assignment.group(2).lstrip().startswith("("):
                rhs = assignment.group(2)
                for field in expected_struct_fields:
                    for match in re.finditer(rf"(?<![A-Za-z0-9_.\[\]-]){re.escape(field)}\s*=", rhs, re.I):
                        after = rhs[match.end():].lstrip()
                        if after and not after.startswith('"'):
                            issues.append(f"unquoted_struct_leaf:{number}:{assignment.group(1)}:{field}")
    entries.sort(key=lambda row: (row[0], row[1], row[2], row[3], row[4]))
    duplicates = {
        "section_blocks": sorted(name for name, count in __import__("collections").Counter(sections).items() if count > 1),
        "assignment_names": sorted([list(name) for name, count in __import__("collections").Counter(assignments).items() if count > 1]),
        "struct_leaf_names": sorted([list(name) for name, count in __import__("collections").Counter(logical_fields).items() if count > 1]),
    }
    canonical = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {"encoding": encoding, "entry_count": len(entries), "schema_sha256": sha(canonical), "duplicates": duplicates, "issues": issues, "entries": entries}

def read_archive(path: Path, source_schema: dict | None = None) -> dict:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"ZIP CRC failure: {bad}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP members")
        members = {name.replace("\\", "/"): archive.read(name) for name in names}
    ints = {name: payload for name, payload in members.items() if name.lower().endswith(INT_SUFFIX)}
    if len(ints) != 658:
        raise ValueError(f"expected 658 INT members, got {len(ints)}")
    schema_by_file = (source_schema or {}).get("struct_string_fields", {})
    reports = {name: analyze_int(payload, set(schema_by_file.get(Path(name).name.casefold(), []))) for name, payload in sorted(ints.items())}
    failures = {name: report["issues"] for name, report in reports.items() if report["issues"]}
    if failures:
        raise ValueError(f"INT format issues: {failures}")
    return {"members": {name: sha(payload) for name, payload in sorted(members.items())}, "int_schema": {name: {"encoding": report["encoding"], "entry_count": report["entry_count"], "schema_sha256": report["schema_sha256"], "duplicates": report["duplicates"]} for name, report in reports.items()}}

def verify(path: Path, baseline: dict, source_schema: dict | None = None) -> None:
    actual = read_archive(path, source_schema)
    package_key = "lite" if "lite" in path.name.casefold() else "full_int"
    if actual != baseline[package_key]:
        raise ValueError(f"release structure/content fingerprint differs from baseline: {path}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path)
    parser.add_argument("--baseline", type=Path, default=Path(__file__).resolve().parents[1] / "tests/fixtures/int_release_baseline.json")
    parser.add_argument("--source-schema", type=Path, default=Path(__file__).resolve().parents[1] / "tests/fixtures/int_source_schema.json")
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    source_schema = json.loads(args.source_schema.read_text("utf-8"))
    for package in args.packages:
        verify(package, baseline, source_schema)
        print(f"OK {package}: 658 INT structures, tokens, all ZIP members")

if __name__ == "__main__":
    main()
