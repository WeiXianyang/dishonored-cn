"""Validate concrete player tutorial coverage in an installed tree or release ZIP."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

INT = "DishonoredGame/Localization/INT/"
PLAYERS = {
    "Twk_Pawn_DefaultPlayer.int": ["Twk_Pawn_DefaultPlayer DisTweaks_PlayerPawn"],
    "Twk_Pawn_Corvo.int": [
        "Twk_Pawn_Corvo DisTweaks_PlayerPawn",
        "Twk_Pawn_Corvo_Release DisTweaks_PlayerPawn",
    ],
    "DLC06_Twk_Player_Daud.int": [
        "DLC06_Twk_Player_Daud DisDLC06Tweaks_PlayerPawn",
        "DLC06_Twk_Player_Daud_Release DisDLC06Tweaks_PlayerPawn",
    ],
    "DLC07_Twk_Player_Daud.int": [
        "DLC07_Twk_Player_Daud DisDLC07Tweaks_PlayerPawn",
        "DLC07_Twk_Player_Daud_Release DisDLC07Tweaks_PlayerPawn",
    ],
}
TOKENS = {
    "m_BlockTutorialMessage": ["GBA_Block"],
    "m_PerfectBlockTutorialMessage": ["GBA_Block"],
    "m_ThrowMovableTutorialMessage": ["GBA_Primary"],
    "m_HeartTargetTutorialMessage": [],
    "m_WheelTutorialMessage": ["GBA_Wheel"],
    "m_WheelTutorialNoteTitle": ["GBA_Journal"],
    "m_DropAssassinationNoteTitle": ["GBA_Journal"],
    "m_PowerInhibitedMessage": [],
}
for family in ("Acquired", "Use"):
    for index, (button, action) in enumerate(
        (("KEY_B", "GBA_HealthElixir"), ("KEY_X", "GBA_ManaElixir"))
    ):
        TOKENS[f"m_{family}ElixirTutorialMessage[{index}]"] = ["GBA_Wheel", button]
        TOKENS[f"m_{family}ElixirTutorialMessage_PC[{index}]"] = [action]


def parse_int(data):
    if not data.startswith(b"\xff\xfe"):
        raise ValueError("player INT must be UTF-16 LE with BOM")
    sections = {}
    section = None
    for line in data.decode("utf-16").lstrip("\ufeff").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section in sections:
                raise ValueError(f"duplicate section: {section}")
            sections[section] = {}
        elif "=" in line and section is not None:
            key, value = line.split("=", 1)
            if key in sections[section]:
                raise ValueError(f"duplicate field: {section}:{key}")
            sections[section][key] = value
    return sections


def verify_player(name, data):
    sections = parse_int(data)
    for section in PLAYERS[name]:
        fields = sections.get(section, {})
        for key, expected_tokens in TOKENS.items():
            if key not in fields:
                raise ValueError(f"{name}:{section}: missing {key}")
            value = fields[key]
            if not (value.startswith('"') and value.endswith('"')):
                raise ValueError(f"{name}:{section}:{key}: invalid quoting")
            if "?INT?" in value or "+++" in value:
                raise ValueError(f"{name}:{section}:{key}: unresolved resource marker")
            if re.findall(r"`([^`]*)`", value) != expected_tokens or value.count("`") != 2 * len(expected_tokens):
                raise ValueError(f"{name}:{section}:{key}: damaged input tokens")
            # DefaultPlayer deliberately has no Overseer warning; concrete pawns do.
            if not (name == "Twk_Pawn_DefaultPlayer.int" and key == "m_PowerInhibitedMessage"):
                if not re.search(r"[\u4e00-\u9fff]", value):
                    raise ValueError(f"{name}:{section}:{key}: empty/untranslated prompt")


def verify(path):
    path = Path(path)
    if path.is_dir():
        for name in PLAYERS:
            verify_player(name, (path / INT / name).read_bytes())
        return
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError(f"ZIP CRC failure: {path}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive members")
        if len([name for name in names if name.lower().endswith(".int")]) != 658:
            raise ValueError("expected 658 INT resources")
        for name in PLAYERS:
            verify_player(name, archive.read(INT + name))
        if "hashes.json" in names:
            entries = json.loads(archive.read("hashes.json"))["entries"]
            # A manifest cannot contain its own final hash. Legacy packages did.
            if "hashes.json" in entries:
                raise ValueError("hashes.json must not hash itself")
            if {n.replace("\\", "/") for n in entries} != set(names) - {"hashes.json"}:
                raise ValueError("hash inventory does not match archive")
            for name, digest in entries.items():
                actual = hashlib.sha256(archive.read(name.replace("\\", "/"))).hexdigest()
                if actual != digest.lower():
                    raise ValueError(f"hash mismatch: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path)
    args = parser.parse_args()
    for package in args.packages:
        verify(package)
        print(f"OK {package}: 7 player sections, 112 tutorial fields")
