# -*- coding: utf-8 -*-
"""从英文 Dishonored UPK 精确恢复天邈 ``texts.db`` 对应的原文。

实现依据是天邈 1.4 自带 ``Sub_Import/library.zip:batch.pyo`` 的实际
Python 2 字节码逻辑：

* ``dis.db`` 的顶层 key 对应 UPK 文件名（不含扩展名，小写）；
* 第二、三层定位 UE3 对话对象；
* 标量值是 ``MD5(英文 UTF-16LE 字节)``；列表值是玩家选项的哈希列表；
* 对话正文位于 ``DisConv_Blurb.m_Text``，玩家选项位于
  ``DisConv_PlayerChoice`` 的 ``m_Choice*.m_ChoiceText``。

游戏目录始终只读。压缩 UPK 由天邈附带的 ``decompress.exe`` 解到系统
临时目录，逐文件解析后立即清理。可复跑缓存和最终产物只写入工作区
``data/``。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import pickle
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import parse_textsdb
from phase1_extract import extract_tags, json_write, jsonl_write, read_upklist, sha256_file


PACKAGE_MAGIC = 0x9E2A83C1
DIALOG_CLASSES = {'DisConv_Blurb', 'DisConv_NonWord', 'DisConv_PlayerChoice'}
HASH_RE = re.compile(r'^[0-9A-F]{32}$')
PARSER_VERSION = 3
RELEASE_ORDER = {
    'base_game': 0,
    'dunwall_city_trials': 1,
    'knife_of_dunwall': 2,
    'brigmore_witches': 3,
    'unknown': 99,
}


class UPKError(Exception):
    """UPK 结构不满足天邈工具所使用的 Dishonored UE3 格式。"""


def decode_ascii(value):
    if isinstance(value, bytes):
        return value.decode('latin1')
    return str(value)


def decode_hash(value):
    text = decode_ascii(value)
    if not HASH_RE.fullmatch(text):
        raise ValueError(f'非法字幕哈希: {text!r}')
    return text


def release_for_upk(stem):
    lower = stem.casefold()
    if 'dlc05' in lower:
        return 'dunwall_city_trials'
    if 'dlc06' in lower:
        return 'knife_of_dunwall'
    if 'dlc07' in lower:
        return 'brigmore_witches'
    return 'base_game'


def load_dis_index(path):
    """解析 Python 2 pickle，保留标量字幕和玩家选择项的全部上下文。"""
    with open(path, 'rb') as f:
        raw = pickle.load(f, encoding='bytes')

    expected = {}
    contexts = defaultdict(list)
    nonword_metadata = 0
    scalar_refs = 0
    choice_refs = 0

    for upk_raw, paths in raw.items():
        upk = decode_ascii(upk_raw).casefold()
        upk_entries = {}
        for dialog_path_raw, objects in paths.items():
            dialog_path = decode_ascii(dialog_path_raw)
            for object_name_raw, value in objects.items():
                object_name = decode_ascii(object_name_raw)
                key = (dialog_path.casefold(), object_name)
                if isinstance(value, bytes):
                    hashes = [decode_hash(value)]
                    kind = 'subtitle'
                    scalar_refs += 1
                elif isinstance(value, list):
                    hashes = [decode_hash(item) for item in value]
                    kind = 'player_choice'
                    choice_refs += len(hashes)
                elif isinstance(value, dict):
                    # DisConv_NonWord 元数据：没有可翻译的 m_Text，天邈也不会注入。
                    nonword_metadata += 1
                    continue
                else:
                    raise ValueError(
                        f'dis.db 未知值类型: {upk}/{dialog_path}/{object_name}: '
                        f'{type(value).__name__}')
                if key in upk_entries:
                    raise ValueError(f'dis.db 重复对象: {upk}/{key}')
                upk_entries[key] = hashes
                for choice_index, digest in enumerate(hashes):
                    contexts[digest].append({
                        'upk': upk,
                        'dialog_path': dialog_path,
                        'object': object_name,
                        'kind': kind,
                        'choice_index': choice_index if kind == 'player_choice' else None,
                        'release': release_for_upk(upk),
                    })
        expected[upk] = upk_entries

    for digest in contexts:
        contexts[digest].sort(key=lambda row: (
            row['upk'], row['dialog_path'].casefold(), row['object'],
            -1 if row['choice_index'] is None else row['choice_index']))
    return expected, dict(contexts), {
        'upk_count': len(expected),
        'object_count': sum(len(entries) for entries in expected.values()),
        'scalar_references': scalar_refs,
        'choice_references': choice_refs,
        'subtitle_references': scalar_refs + choice_refs,
        'unique_hashes': len(contexts),
        'nonword_metadata_objects': nonword_metadata,
    }


def read_exact(stream, size, label):
    data = stream.read(size)
    if len(data) != size:
        raise UPKError(f'{label}: 需要 {size} 字节，实际 {len(data)} 字节')
    return data


def name_index(value, names):
    # UE3 FName 是 index + instance number；天邈脚本把 64 位值直接作为 index。
    # Dishonored 的属性 tag 中高 32 位为 0。这里显式拆低位，并拒绝异常高位。
    index = value & 0xFFFFFFFF
    number = value >> 32
    if number:
        raise UPKError(f'属性 FName 含非零 instance number: {value:#x}')
    if index >= len(names):
        raise UPKError(f'FName 索引越界: {index} >= {len(names)}')
    return index


def read_name_ref(stream, names, label):
    value, = struct.unpack('<Q', read_exact(stream, 8, label))
    return names[name_index(value, names)]


def decode_fstring(stream):
    length, = struct.unpack('<i', read_exact(stream, 4, 'FString 长度'))
    if length > 0:
        raw = read_exact(stream, length, 'ANSI FString')
        return raw.rstrip(b'\0').decode('latin1')
    if length < 0:
        raw = read_exact(stream, -length * 2, 'UTF-16 FString')
        return raw.decode('utf-16-le').rstrip('\0')
    return ''


def read_property(stream, names):
    """移植天邈 ``batch.py:do_next``，返回 (name, type, value)。"""
    name = read_name_ref(stream, names, '属性名')
    if name == 'None':
        return name, None, None
    prop_type = read_name_ref(stream, names, '属性类型')
    size, = struct.unpack('<Q', read_exact(stream, 8, '属性长度'))

    if prop_type == 'StrProperty':
        return name, prop_type, decode_fstring(stream)
    if prop_type == 'FloatProperty':
        value, = struct.unpack('<f', read_exact(stream, 4, name))
        return name, prop_type, value
    if prop_type in ('ObjectProperty', 'IntProperty'):
        value, = struct.unpack('<i', read_exact(stream, 4, name))
        return name, prop_type, value
    if prop_type == 'BoolProperty':
        value, = struct.unpack('<B', read_exact(stream, 1, name))
        return name, prop_type, bool(value)
    if prop_type == 'NameProperty':
        return name, prop_type, read_name_ref(stream, names, name)
    if prop_type == 'ArrayProperty':
        return name, prop_type, read_exact(stream, size, name)
    if prop_type == 'StructProperty' and name == 'm_iBlurbGUID':
        raw = read_exact(stream, size + 8, name)
        return name, prop_type, raw[8:24]
    if prop_type in ('StructProperty', 'ByteProperty'):
        read_exact(stream, size + 8, name)
        return name, prop_type, None
    raise UPKError(f'不支持的属性类型: {name}/{prop_type}，offset={stream.tell()}')


def parse_choice_array(raw, names):
    stream = io.BytesIO(raw)
    count, = struct.unpack('<i', read_exact(stream, 4, '玩家选择数量'))
    if count < 0 or count > 1000:
        raise UPKError(f'异常玩家选择数量: {count}')
    choices = []
    for _index in range(count):
        text = None
        while True:
            name, prop_type, value = read_property(stream, names)
            if name == 'None':
                break
            if name == 'm_ChoiceText' and prop_type == 'StrProperty':
                text = value
        if text is None:
            raise UPKError('玩家选择项缺少 m_ChoiceText')
        choices.append(text)
    return choices


def load_upk_tables(path):
    """读取天邈注入器所依赖的 Name/Import/Export 表。"""
    with open(path, 'rb') as f:
        magic, file_version, data_offset, folder_name_size = struct.unpack(
            '<IIII', read_exact(f, 16, 'UPK 头'))
        if magic != PACKAGE_MAGIC:
            raise UPKError(f'未知 UPK magic: {magic:#x}')
        f.seek(folder_name_size, os.SEEK_CUR)
        f.seek(4, os.SEEK_CUR)
        base_info_offset = f.tell()
        name_count, name_offset, export_count, export_offset, import_count, import_offset = (
            struct.unpack('<iIiIiI', read_exact(f, 24, 'UPK 表索引')))
        read_exact(f, 12, 'UPK generation 信息')
        net_object_count, engine_version, cooker_version = struct.unpack(
            '<III', read_exact(f, 12, 'UPK 版本信息'))

        f.seek(name_offset)
        names = []
        for _ in range(name_count):
            length, = struct.unpack('<i', read_exact(f, 4, 'Name 长度'))
            if length > 0:
                value = read_exact(f, length, 'ANSI Name').rstrip(b'\0').decode('latin1')
            elif length < 0:
                value = read_exact(f, -length * 2, 'UTF-16 Name').decode(
                    'utf-16-le').rstrip('\0')
            else:
                value = ''
            read_exact(f, 8, 'Name flags')
            names.append(value)

        f.seek(import_offset)
        imports = []
        for _ in range(import_count):
            values = struct.unpack('<qiiiii', read_exact(f, 28, 'Import'))
            imports.append({
                'base_pack': values[0],
                'type': values[1],
                'pack_name': values[3],
                'name': values[4],
            })

        f.seek(export_offset)
        exports = []
        object_ref_count = 0
        for _ in range(export_count):
            record_offset = f.tell()
            values = struct.unpack('<12i', read_exact(f, 48, 'Export'))
            exports.append({
                'name': values[3],
                'class': values[0],
                'group': values[2] - 1,
                'size': values[8],
                'offset': values[9],
                'num': values[4] - 1,
                'record_offset': record_offset,
            })
            if values[11] > 0:
                object_ref_count += 1
                read_exact(f, 24, 'Export 扩展 A')
            else:
                read_exact(f, 20, 'Export 扩展 B')

        for export in exports:
            try:
                export['object_name'] = names[export['name']]
                if export['num'] >= 0:
                    export['object_name'] += f"_{export['num']}"
                class_ref = export['class']
                if class_ref < 0:
                    export['class_name'] = names[imports[-class_ref - 1]['name']]
                elif class_ref > 0:
                    export['class_name'] = names[exports[class_ref - 1]['name']]
                else:
                    export['class_name'] = 'Class'
            except IndexError as exc:
                raise UPKError(f'Export 名称/类型索引越界: {export}') from exc

        for index, export in enumerate(exports):
            groups = []
            current = index
            visited = set()
            while exports[current]['group'] >= 0:
                if current in visited:
                    raise UPKError(f'Export group 出现环: {index}')
                visited.add(current)
                parent_index = exports[current]['group']
                if parent_index >= len(exports):
                    raise UPKError(f'Export group 越界: {parent_index}')
                parent = exports[parent_index]
                group_name = names[parent['name']]
                if parent['num'] >= 0:
                    group_name += f"_{parent['num']}"
                group_name += '.' if parent['class_name'] == 'Package' else ':'
                groups.append(group_name)
                current = parent_index
            groups.reverse()
            export['group_path'] = ''.join(groups)[:-1] if groups else ''

    return {
        'file_version': file_version,
        'data_offset': data_offset,
        'base_info_offset': base_info_offset,
        'engine_version': engine_version,
        'cooker_version': cooker_version,
        'net_object_count': net_object_count,
        'object_ref_count': object_ref_count,
        'names': names,
        'imports': imports,
        'exports': exports,
    }


def text_hash(text):
    return hashlib.md5(text.encode('utf-16-le')).hexdigest().upper()


def extract_expected_from_upk(path, expected_entries):
    """按 dis.db 的对象坐标读取目标英文串，并做 MD5 强校验。"""
    tables = load_upk_tables(path)
    names = tables['names']
    extracted = {}
    observations = []
    issues = []
    seen_objects = set()

    with open(path, 'rb') as f:
        for export in tables['exports']:
            if export['class_name'] not in DIALOG_CLASSES:
                continue
            key = (export['group_path'].casefold(), export['object_name'])
            if key not in expected_entries:
                continue
            seen_objects.add(key)
            f.seek(export['offset'])
            raw = read_exact(f, export['size'], f"Export {key}")
            stream = io.BytesIO(raw)
            read_exact(stream, 4, 'Export 前缀')
            subtitle = None
            choice_candidates = []
            while True:
                try:
                    name, prop_type, value = read_property(stream, names)
                except UPKError as exc:
                    issues.append({
                        'type': 'property_parse_error',
                        'dialog_path': key[0],
                        'object': key[1],
                        'detail': str(exc),
                    })
                    break
                if name == 'None':
                    break
                if name == 'm_Text' and prop_type == 'StrProperty':
                    subtitle = value
                elif name.startswith('m_Choice') and prop_type == 'ArrayProperty':
                    try:
                        choice_candidates.append((name, parse_choice_array(value, names)))
                    except UPKError as exc:
                        issues.append({
                            'type': 'choice_parse_error',
                            'dialog_path': key[0],
                            'object': key[1],
                            'detail': str(exc),
                        })

            expected_hashes = expected_entries[key]
            # 玩家选择对象即使只有一个选项，也可能同时带内部调试用途的
            # m_Text（例如 "[Challenge Butchers]"）。天邈注入器按对象类别
            # 始终改 m_Choice* 数组，不能用“哈希数量 > 1”来猜字段。
            if export['class_name'] == 'DisConv_PlayerChoice':
                exact_candidates = [
                    texts for _name, texts in choice_candidates
                    if [text_hash(text) for text in texts] == expected_hashes
                ]
                # 部分对象同时有 Static 与 Optional 数组；dis.db 的哈希对应
                # 其中真正显示的数组，不能简单取最后遇到的一个。
                actual_texts = exact_candidates[0] if exact_candidates else (
                    choice_candidates[0][1] if choice_candidates else None)
            else:
                actual_texts = [subtitle] if subtitle is not None else None
            if actual_texts is None:
                issues.append({
                    'type': 'text_property_missing',
                    'dialog_path': key[0],
                    'object': key[1],
                    'expected_hashes': expected_hashes,
                })
                continue
            if len(actual_texts) != len(expected_hashes):
                issues.append({
                    'type': 'choice_count_mismatch',
                    'dialog_path': key[0],
                    'object': key[1],
                    'expected_count': len(expected_hashes),
                    'actual_count': len(actual_texts),
                })
            for index, (expected_hash, text) in enumerate(zip(expected_hashes, actual_texts)):
                actual_hash = text_hash(text)
                observation = {
                    'hash': expected_hash,
                    'dialog_path': key[0],
                    'object': key[1],
                    'choice_index': index if export['class_name'] == 'DisConv_PlayerChoice' else None,
                    'computed_hash': actual_hash,
                }
                observations.append(observation)
                if actual_hash != expected_hash:
                    issues.append({
                        'type': 'hash_mismatch',
                        **observation,
                        'text': text,
                    })
                    continue
                previous = extracted.setdefault(expected_hash, text)
                if previous != text:
                    raise UPKError(f'同一哈希对应不同英文: {expected_hash}')

    for dialog_path, object_name in sorted(set(expected_entries) - seen_objects):
        issues.append({
            'type': 'object_not_found',
            'dialog_path': dialog_path,
            'object': object_name,
            'expected_hashes': expected_entries[(dialog_path, object_name)],
        })
    return extracted, observations, issues, {
        'name_count': len(tables['names']),
        'export_count': len(tables['exports']),
        'import_count': len(tables['imports']),
        'dialog_export_count': sum(
            export['class_name'] in DIALOG_CLASSES for export in tables['exports']),
        'file_version': tables['file_version'],
        'engine_version': tables['engine_version'],
        'cooker_version': tables['cooker_version'],
    }


def load_integrity_hashes(project_root):
    path = Path(project_root) / 'data' / 'raw' / 'manifests' / 'source_integrity_before.json'
    if not path.is_file():
        raise SystemExit('缺少 Phase 1 源哈希基线，请先运行 phase1_extract.py')
    data = json.load(open(path, encoding='utf-8'))
    return {
        (row['side'], row['path'].replace('\\', '/').casefold()): row
        for row in data['files']
    }


def expected_signature(entries):
    normalized = [
        [path, name, hashes]
        for (path, name), hashes in sorted(entries.items())
    ]
    return hashlib.sha256(json.dumps(
        normalized, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def decompress_and_extract(src, decompressor_src, expected_entries):
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='dh_upk_') as temp:
        temp = Path(temp)
        local_decompressor = temp / 'decompress.exe'
        shutil.copy2(decompressor_src, local_decompressor)
        output_dir = temp / 'unpacked'
        command = [str(local_decompressor), f'-out={output_dir}', str(src)]
        result = subprocess.run(
            command, cwd=temp, capture_output=True, text=True,
            encoding='utf-8', errors='replace', check=False)
        unpacked = output_dir / src.name
        if result.returncode != 0 or not unpacked.is_file():
            raise UPKError(
                f'decompress 失败 rc={result.returncode}: '
                f'{(result.stdout + result.stderr).strip()[-1000:]}')
        values, observations, issues, tables = extract_expected_from_upk(
            unpacked, expected_entries)
        report = {
            'decompress_returncode': result.returncode,
            'compressed_size': src.stat().st_size,
            'uncompressed_size': unpacked.stat().st_size,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            **tables,
        }
        return values, observations, issues, report


def cache_path(parts_dir, stem):
    safe = re.sub(r'[^a-z0-9_.-]+', '_', stem.casefold())
    return parts_dir / f'{safe}.json'


def load_part(path, source_hash, signature, decompressor_hash):
    if not path.is_file():
        return None
    try:
        data = json.load(open(path, encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    expected = {
        'parser_version': PARSER_VERSION,
        'source_sha256': source_hash,
        'expected_signature': signature,
        'decompressor_sha256': decompressor_hash,
    }
    if any(data.get(key) != value for key, value in expected.items()):
        return None
    return data


def write_upk_sample(path, rows, count=50):
    ranked = sorted(
        (row for row in rows if row['status'] == 'aligned'),
        key=lambda row: hashlib.sha256(row['id'].encode()).hexdigest())[:count]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'id', 'primary_release', 'upk', 'dialog_path', 'object',
            'choice_index', 'en', 'cn', 'alignment_ok', 'note'])
        writer.writeheader()
        for row in ranked:
            primary = row['context']['references'][0]
            writer.writerow({
                'id': row['id'],
                'primary_release': row['domain']['primary_release'],
                'upk': primary['upk'],
                'dialog_path': primary['dialog_path'],
                'object': primary['object'],
                'choice_index': primary['choice_index'],
                'en': row['en'],
                'cn': row['cn'],
                'alignment_ok': '',
                'note': '',
            })
    return len(ranked)


def build_outputs(project, cn_db, contexts, recovered, file_reports, all_issues,
                  dis_stats, selected_count, total_count, decompressor_hash):
    raw_dir = project / 'data' / 'raw'
    aligned_dir = project / 'data' / 'aligned'
    context_json = {
        digest: refs for digest, refs in sorted(contexts.items())
    }
    json_write(raw_dir / 'dis_context.json', context_json)
    json_write(raw_dir / 'upk_en_texts.json', dict(sorted(recovered.items())))

    rows = []
    for digest, cn_text in sorted(cn_db.items()):
        refs = contexts.get(digest, [])
        releases = sorted({ref['release'] for ref in refs})
        primary_release = min(
            releases, key=lambda value: RELEASE_ORDER.get(value, 98)) if releases else 'unknown'
        en_text = recovered.get(digest, '')
        nul_terminated = cn_text.endswith('\0')
        cn_payload = cn_text[:-1] if nul_terminated else cn_text
        rows.append({
            'id': f'upk:{digest}',
            'layer': 'upk',
            'context': {
                'hash': digest,
                'references': refs,
            },
            'source_context': {
                'method': 'ue3_property_from_english_upk',
                'hash_algorithm': 'MD5(UTF-16LE)',
            },
            'domain': {
                'releases': releases,
                'primary_release': primary_release,
                'long_text': max(len(en_text), len(cn_payload)) >= 240,
            },
            'target_format': {'nul_terminated': nul_terminated},
            'en': en_text,
            'cn': cn_payload,
            # 校对写回必须保留的是天邈目标串中的格式标记；英文仅作语义源，
            # 其 token 不应被强制塞入中文。
            # 保留每次出现；重复的口型/换行标记同样是写回契约的一部分。
            'tags': extract_tags(cn_payload),
            'status': 'aligned' if digest in recovered else 'en_missing',
        })
    jsonl_write(aligned_dir / 'upk_corpus.jsonl', rows)

    missing = sorted(set(cn_db) - set(recovered))
    contexts_missing = sorted(set(cn_db) - set(contexts))
    unknown_context_hashes = sorted(set(contexts) - set(cn_db))
    json_write(aligned_dir / 'upk_alignment_issues.json', {
        'english_missing': missing,
        'context_missing': contexts_missing,
        'context_hash_not_in_texts_db': unknown_context_hashes,
        'extraction_issues': all_issues,
    })

    primary_counts = Counter(row['domain']['primary_release'] for row in rows)
    primary_recovered = Counter(
        row['domain']['primary_release'] for row in rows if row['status'] == 'aligned')
    release_refs = Counter()
    release_ref_recovered = Counter()
    for row in rows:
        for release in row['domain']['releases']:
            release_refs[release] += 1
            if row['status'] == 'aligned':
                release_ref_recovered[release] += 1
    dlc_coverage = {
        'unique_by_primary_release': {
            release: {
                'total': primary_counts[release],
                'english_recovered': primary_recovered[release],
                'chinese_nonempty': sum(
                    bool(row['cn']) for row in rows
                    if row['domain']['primary_release'] == release),
                'suspected_english_residue': sum(
                    bool(re.search(
                        r'[A-Za-z]{4,}',
                        re.sub(r'<[^>]*>|`[^`]*`', '', row['cn'])))
                    for row in rows if row['domain']['primary_release'] == release),
            }
            for release in sorted(primary_counts)
        },
        'unique_hashes_referenced_by_release': {
            release: {
                'total': release_refs[release],
                'english_recovered': release_ref_recovered[release],
            }
            for release in sorted(release_refs)
        },
        'note': '共享台词可被多个版本引用；primary 统计互斥，referenced 统计允许重复。',
    }
    json_write(aligned_dir / 'dlc_coverage.json', dlc_coverage)

    manifest = {
        'schema_version': 1,
        'method': 'Port of Tianmiao 1.4 batch.pyo UE3 object/property reader',
        'hash_algorithm': 'MD5(English text encoded as UTF-16LE, no terminator)',
        'parser_version': PARSER_VERSION,
        'decompressor_sha256': decompressor_hash,
        'dis_db': dis_stats,
        'upk_files_selected': selected_count,
        'upk_files_total': total_count,
        'texts_db_entries': len(cn_db),
        'context_hashes': len(contexts),
        'english_recovered': len(recovered),
        'english_missing': len(missing),
        'file_reports': file_reports,
    }
    json_write(raw_dir / 'upk_extraction_manifest.json', manifest)
    sample_count = write_upk_sample(aligned_dir / 'upk_sample_review.csv', rows)
    return manifest, len(rows), sample_count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--en-root', required=True)
    ap.add_argument('--cn-root', required=True)
    ap.add_argument('--project-root', default=os.path.dirname(os.path.dirname(__file__)))
    ap.add_argument('--only-upk', action='append', default=[],
                    help='仅处理指定 stem；可重复，用于技术验证')
    ap.add_argument('--no-resume', action='store_true')
    args = ap.parse_args()

    project = Path(args.project_root).resolve()
    en_root = Path(args.en_root).resolve()
    cn_root = Path(args.cn_root).resolve()
    dis_path = cn_root / 'Sub_Import' / 'dis.db'
    texts_path = cn_root / 'Sub_Import' / 'texts.db'
    decompressor = cn_root / 'Sub_Import' / 'decompress.exe'
    if not all(path.is_file() for path in (dis_path, texts_path, decompressor)):
        raise SystemExit('中文源缺少 dis.db/texts.db/decompress.exe')

    cn_db = parse_textsdb.parse_textsdb(texts_path)
    expected, contexts, dis_stats = load_dis_index(dis_path)
    if set(cn_db) != set(contexts):
        missing_context = sorted(set(cn_db) - set(contexts))
        extra_context = sorted(set(contexts) - set(cn_db))
        raise SystemExit(
            f'texts.db 与 dis.db 哈希集合不一致: '
            f'无上下文 {len(missing_context)}，无中文 {len(extra_context)}')

    integrity = load_integrity_hashes(project)
    decompressor_hash = sha256_file(decompressor)
    upk_relatives = read_upklist(cn_root)
    stems = {Path(relative).stem.casefold(): relative for relative in upk_relatives}
    if len(stems) != len(upk_relatives):
        raise SystemExit('upklist.db 存在重复 stem')
    if set(stems) != set(expected):
        raise SystemExit(
            f'upklist/dis.db 顶层集合不一致: '
            f'list_only={sorted(set(stems)-set(expected))}, '
            f'dis_only={sorted(set(expected)-set(stems))}')

    requested = {item.casefold().removesuffix('.upk') for item in args.only_upk}
    unknown = requested - set(stems)
    if unknown:
        raise SystemExit(f'--only-upk 不存在: {sorted(unknown)}')
    selected = sorted(requested or stems)
    parts_dir = project / 'data' / 'raw' / 'upk_parts'
    parts_dir.mkdir(parents=True, exist_ok=True)

    recovered = {}
    file_reports = []
    all_issues = []
    total = len(selected)
    for number, stem in enumerate(selected, 1):
        relative = stems[stem]
        src = en_root.joinpath(*relative.replace('\\', '/').split('/'))
        if not src.is_file():
            raise SystemExit(f'英文 UPK 缺失: {src}')
        integrity_row = integrity.get(('en', relative.replace('\\', '/').casefold()))
        if integrity_row is None:
            raise SystemExit(f'UPK 不在源哈希基线: {relative}')
        signature = expected_signature(expected[stem])
        part_file = cache_path(parts_dir, stem)
        part = None if args.no_resume else load_part(
            part_file, integrity_row['sha256'], signature, decompressor_hash)
        if part is None:
            print(f'[{number}/{total}] 解压并解析 {relative}', flush=True)
            values, observations, issues, report = decompress_and_extract(
                src, decompressor, expected[stem])
            part = {
                'parser_version': PARSER_VERSION,
                'source_sha256': integrity_row['sha256'],
                'expected_signature': signature,
                'decompressor_sha256': decompressor_hash,
                'upk': stem,
                'relative_path': relative,
                'values': values,
                'observations': observations,
                'issues': issues,
                'report': report,
            }
            json_write(part_file, part)
        else:
            print(f'[{number}/{total}] 缓存命中 {relative}', flush=True)

        for digest, text in part['values'].items():
            previous = recovered.setdefault(digest, text)
            if previous != text:
                raise SystemExit(f'跨 UPK 同哈希英文不一致: {digest}')
        report = {
            'upk': stem,
            'relative_path': relative,
            'expected_objects': len(expected[stem]),
            'expected_hash_references': sum(len(v) for v in expected[stem].values()),
            'recovered_unique_hashes': len(part['values']),
            'issue_count': len(part['issues']),
            'cache': part_file.name,
            **part['report'],
        }
        file_reports.append(report)
        for issue in part['issues']:
            all_issues.append({'upk': stem, **issue})

    manifest, row_count, sample_count = build_outputs(
        project, cn_db, contexts, recovered, file_reports, all_issues,
        dis_stats, len(selected), len(stems), decompressor_hash)
    print(json.dumps({
        'upk_files': f"{len(selected)}/{len(stems)}",
        'dis_db': dis_stats,
        'texts_db_entries': len(cn_db),
        'english_recovered': manifest['english_recovered'],
        'english_missing': manifest['english_missing'],
        'corpus_rows': row_count,
        'extraction_issues': len(all_issues),
        'sample_rows': sample_count,
    }, ensure_ascii=False, indent=1))

    if not requested and (manifest['english_missing'] or all_issues):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
