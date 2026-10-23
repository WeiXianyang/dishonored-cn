"""Regression mutations against the actual shipping packages."""

from pathlib import Path
import hashlib
import json
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_player_prompts import INT, PLAYERS, parse_int, verify, verify_player


class PlayerPromptsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(ROOT / "Dishonored-CN-1.4p-Lite.zip") as archive:
            cls.players = {name: archive.read(INT + name) for name in PLAYERS}

    def test_all_shipping_copies(self):
        for relative in ("Dishonored-CN-1.4p-Lite.zip", "release/Dishonored-CN-1.4p-Lite.zip", "release/Dishonored-CN-1.4p-Full-part1-INT.zip"):
            with self.subTest(package=relative):
                verify(ROOT / relative)

    def test_every_concrete_pc_field_is_required(self):
        # Deleting any one field must fail even if DefaultPlayer still has it.
        for name, data in self.players.items():
            for section, fields in parse_int(data).items():
                if section not in PLAYERS[name]:
                    continue
                for key, value in fields.items():
                    if "ElixirTutorialMessage_PC[" not in key:
                        continue
                    with self.subTest(file=name, section=section, key=key):
                        text = data.decode("utf-16")
                        start = text.index("[" + section + "]")
                        index = text.index(key + "=" + value, start)
                        broken = text[:index] + text[index + len(key + "=" + value):]
                        with self.assertRaisesRegex(ValueError, "missing"):
                            verify_player(name, broken.encode("utf-16"))

    def test_damaged_or_fixed_key_tokens_are_rejected(self):
        name = "Twk_Pawn_Corvo.int"
        for bad in ("`GBA_生命药剂`", "R", "`GBA_healthelixir`", "`GBA_HealthElixir", "`GBA_ManaElixir`"):
            with self.subTest(token=bad):
                text = self.players[name].decode("utf-16").replace("`GBA_HealthElixir`", bad, 1)
                with self.assertRaisesRegex(ValueError, "tokens"):
                    verify_player(name, text.encode("utf-16"))

    def test_corvo_pc_prompts_match_default_player(self):
        template = parse_int(self.players["Twk_Pawn_DefaultPlayer.int"])[PLAYERS["Twk_Pawn_DefaultPlayer.int"][0]]
        corvo = parse_int(self.players["Twk_Pawn_Corvo.int"])
        for section in PLAYERS["Twk_Pawn_Corvo.int"]:
            for key, value in template.items():
                if "ElixirTutorialMessage_PC[" in key:
                    self.assertEqual(corvo[section][key], value, f"{section}:{key}")

    def test_duplicate_field_is_rejected(self):
        name = "Twk_Pawn_Corvo.int"
        text = self.players[name].decode("utf-16")
        line = 'm_AcquiredElixirTutorialMessage_PC[0]="按 `GBA_HealthElixir` 喝生命药剂。"'
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            verify_player(name, text.replace(line, line + "\r\n" + line, 1).encode("utf-16"))

    def test_all_int_payloads_match(self):
        with zipfile.ZipFile(ROOT / "Dishonored-CN-1.4p-Lite.zip") as lite, zipfile.ZipFile(ROOT / "release/Dishonored-CN-1.4p-Full-part1-INT.zip") as full:
            for name in full.namelist():
                self.assertEqual(lite.read(name), full.read(name), name)
        self.assertEqual((ROOT / "Dishonored-CN-1.4p-Lite.zip").read_bytes(), (ROOT / "release/Dishonored-CN-1.4p-Lite.zip").read_bytes())

    def test_release_manifests_match_packages(self):
        manifest = json.loads((ROOT / "release-manifest.json").read_text("utf-8"))
        self.assertEqual(manifest, json.loads((ROOT / "release/release-manifest.json").read_text("utf-8")))
        for name in ("Dishonored-CN-1.4p-Lite.zip", "Dishonored-CN-1.4p-Full-part1-INT.zip"):
            package = ROOT / "release" / name
            entry = manifest["parts"][name]
            self.assertEqual(entry["sha256"], hashlib.sha256(package.read_bytes()).hexdigest())
            self.assertEqual(entry["size_bytes"], package.stat().st_size)
            with zipfile.ZipFile(package) as archive:
                self.assertEqual(entry["files"], len(archive.infolist()))


if __name__ == "__main__":
    unittest.main()
