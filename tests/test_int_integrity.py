"""Full-package structural/token and known-fix regression tests."""
import json
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from int_schema import decode_int_bytes
from verify_int_integrity import analyze_int, read_archive, verify

INT = "DishonoredGame/Localization/INT/"
BASELINE = json.loads((ROOT / "tests/fixtures/int_release_baseline.json").read_text("utf-8"))
SOURCE_SCHEMA = json.loads((ROOT / "tests/fixtures/int_source_schema.json").read_text("utf-8"))
class FullIntIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lite_path = ROOT / "Dishonored-CN-1.4p-Lite.zip"
        cls.full_path = ROOT / "release/Dishonored-CN-1.4p-Full-part1-INT.zip"
        with zipfile.ZipFile(cls.lite_path) as archive:
            cls.members = {name: archive.read(name) for name in archive.namelist()}

    def test_confirmed_packages_match_all_658_schema_and_member_hashes(self):
        verify(self.lite_path, BASELINE, SOURCE_SCHEMA)
        verify(self.full_path, BASELINE, SOURCE_SCHEMA)
        lite = read_archive(self.lite_path, SOURCE_SCHEMA)
        full = read_archive(self.full_path, SOURCE_SCHEMA)
        self.assertEqual(lite["int_schema"], full["int_schema"])
        self.assertEqual(
            {name: digest for name, digest in lite["members"].items() if name.lower().endswith(".int")},
            full["members"],
        )

    def test_bom_mutation_is_rejected(self):
        name = INT + "DLC06_Twk_Player_Daud.int"
        fixed = self.members[name]
        self.assertEqual(analyze_int(fixed)["issues"], [])
        broken = fixed[:2] + b"\xff\xfe" + fixed[2:]
        self.assertIn("embedded_or_duplicate_bom", analyze_int(broken)["issues"])

    def test_leaderboard_delimiter_mutation_is_rejected(self):
        name = INT + "DishonoredGame.int"
        raw = self.members[name]
        text, encoding = decode_int_bytes(raw)
        line = "LeaderboardUserNotConnectedErrorPC=你没有连接到Steam上"
        self.assertIn(line, text)
        broken = text.replace(line, line.replace("PC=", "PC", 1), 1)
        self.assertTrue(any(issue.startswith("missing_equals:") for issue in analyze_int((b"\xff\xfe" + broken.encode("utf-16-le")))["issues"]))

    def test_section_punctuation_mutation_changes_identity_fingerprint(self):
        name = INT + "DLC06_Twk_Store.int"
        raw = self.members[name]
        text, _ = decode_int_bytes(raw)
        self.assertIn("[Tutorial.DLC06_StoreTutorial_PickUp DisTweaks_AbstractItemPickupNote]", text)
        broken = text.replace("[Tutorial.DLC06_StoreTutorial_PickUp", "[Tutorial。DLC06_StoreTutorial_PickUp", 1)
        baseline = analyze_int(raw)
        mutated = analyze_int(b"\xff\xfe" + broken.encode("utf-16-le"))
        self.assertNotEqual(baseline["schema_sha256"], mutated["schema_sha256"])

    def test_dlc05_nonempty_struct_leaves_are_required(self):
        name = INT + "DishonoredGame.int"
        text, _ = decode_int_bytes(self.members[name])
        for index in (0, 1, 2, 7, 8, 9):
            self.assertRegex(text, rf'm_Challenges\[{index}\]=.*m_ExpertModeDesc="[^"]+"')
        self.assertNotRegex(text, r'm_Challenges\[[3456]\]=.*m_ExpertModeDesc=')
        damaged = text.replace(',m_ExpertModeDesc="潜行难度设为极难。线索放在部分人物的腰带上。"', '', 1)
        self.assertNotEqual(analyze_int(self.members[name])["schema_sha256"], analyze_int(b"\xff\xfe" + damaged.encode("utf-16-le"))["schema_sha256"])

    def test_dynamic_resource_token_mutation_changes_fingerprint(self):
        name = INT + "DLC06_Twk_Store.int"
        text, _ = decode_int_bytes(self.members[name])
        self.assertIn("`GBA_Journal`", text)
        broken = text.replace("`GBA_Journal`", "`GBA_journal`", 1)
        self.assertNotEqual(analyze_int(self.members[name])["schema_sha256"], analyze_int(b"\xff\xfe" + broken.encode("utf-16-le"))["schema_sha256"])

    def test_square_brackets_are_not_treated_as_tokens(self):
        parsed = analyze_int(b'[Section]\nLiteral=[ordinary text]\nArray[0]=value\n')
        self.assertEqual(parsed["issues"], [])
        self.assertEqual(parsed["entry_count"], 2)

    def test_duplicate_struct_leaf_is_reported_with_occurrence_preserved(self):
        parsed = analyze_int(b'[Section]\nEntry=(m_Name="one",m_Name="two")\n')
        self.assertEqual(parsed["issues"], [])
        self.assertEqual(parsed["duplicates"]["struct_leaf_names"], [["Section", "Entry", 0, "m_Name"]])
        self.assertEqual([row[4] for row in parsed["entries"]], [0, 1])

    def test_source_confirmed_struct_string_must_stay_quoted(self):
        parsed = analyze_int('[Section]\nEntry=(m_Description=中文)\n'.encode("utf-8"), {"m_Description"})
        self.assertIn("unquoted_struct_leaf:2:Entry:m_Description", parsed["issues"])
        # Unquoted numeric values remain valid because they are not source-confirmed strings.
        numeric = analyze_int(b'[Section]\nEntry=(m_Count=4)\n', {"m_Description"})
        self.assertEqual(numeric["issues"], [])

    def test_dlc07_quote_repair_is_a_real_gate(self):
        name = INT + "DLC07_Twk_Store.int"
        raw = self.members[name]
        self.assertEqual(analyze_int(raw, set(SOURCE_SCHEMA["struct_string_fields"]["dlc07_twk_store.int"]))["issues"], [])
        text, _ = decode_int_bytes(raw)
        fixed = 'm_Description="一种能放在任何平面上的致命陷阱。'
        self.assertIn(fixed, text)
        broken = text.replace(fixed, fixed.replace('m_Description="', 'm_Description=', 1), 1)
        bad = analyze_int(b"\xff\xfe" + broken.encode("utf-16-le"), set(SOURCE_SCHEMA["struct_string_fields"]["dlc07_twk_store.int"]))
        self.assertTrue(any(issue.startswith("unquoted_struct_leaf:") for issue in bad["issues"]))

if __name__ == "__main__":
    unittest.main()
