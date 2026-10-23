# 2026-10-24 全量结构复核

{
  "date": "2026-10-24",
  "baseline_commit": "17e8f366b2370e6e0783098bf20bc5425edc752a",
  "scope": "静态检查全部658个INT、10,284条唯一字幕、151个UPK中的107,913条引用；未启动游戏UI。",
  "repairs": [
    "修正DLC06_Twk_Store两个section中的全角句点，恢复10项section身份。",
    "删除DLC06_Twk_Player_Daud.int、DLC07_Twk_Player_Daud.int、Twk_Pawn_DefaultPlayer.int的第二个UTF-16LE BOM。",
    "为LeaderboardUserNotConnectedErrorPC补回缺失等号，保留原中文。",
    "恢复DLC05六个非空m_ExpertModeDesc结构字段；英文为空的索引3至6仍省略。",
    "为DLC07_Twk_Store.int的m_StoreItems[4].m_Description仅补回开引号（原值已有闭引号），保留原中文。"
  ],
  "intentional_differences": [
    "13组仅大小写不同的section/key身份保持原样，未假定引擎匹配规则。",
    "4个英文为空的DLC05 m_ExpertModeDesc未增加空字段。",
    "Daud的63个目标独有字段、Corvo已存在的8项新增字段及ChapterNotes的3项目标独有字段按来源/UPK证据保留。",
    "22处换行/转义差异未改。"
  ],
  "validation": {
    "int_files": 658,
    "post_repair_source_only": 17,
    "post_repair_target_only": 87,
    "token_differences": 0,
    "subtitle_references": 107913,
    "subtitle_equal_to_db": 107677,
    "subtitle_text_only_differences": 236,
    "subtitle_structure_differences": 0,
    "release_upks_scanned": 151,
    "unquoted_source_string_struct_leaves": 0,
    "game_runtime_tested": false,
    "test_command": "python -m unittest discover -s tests -v",
    "test_result": "17 passed",
    "changelog_json_record_count": 5530,
    "source_only_breakdown": "17 = 13 case-only source identities + 4 empty English ExpertModeDesc values",
    "target_only_breakdown": "87 = 13 case-only target identities + 63 Daud + 8 existing Corvo additions + 3 intentional ChapterNotes fields"
  },
  "packages": {
    "Dishonored-CN-1.4p-Lite.zip": {
      "size_bytes": 29553468,
      "sha256": "49c55e40a8554155a667e6e074c6811c7f765dd4bf8f0e1b9d75fc50b359d8c7"
    },
    "Dishonored-CN-1.4p-Full-part1-INT.zip": {
      "size_bytes": 583480,
      "sha256": "9d15c5cc31d894ada7b9a452925ecdeae4b0f66b367dbf2e6be7b167f28ea07b"
    }
  }
}
