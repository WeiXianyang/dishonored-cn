# -*- coding: utf-8 -*-
"""Phase 1 可复跑提取器：冻结双源、盘点 INT、生成中英对齐语料。

该工具只读游戏目录，所有 JSON/JSONL/CSV 产物写入工作区 ``data/``。
英文 UPK 字幕恢复由后续提取器完成；本工具先固定相关 UPK 的完整性基线。
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import parse_int


def atomic_replace(src, dst, attempts=20, delay=0.1):
    """Windows 索引器/杀软可能短暂打开旧文件；有限重试仍保持原子语义。"""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt + 1 == attempts:
                raise
            time.sleep(delay)


def json_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write('\n')
    atomic_replace(tmp, path)


def jsonl_write(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
    atomic_replace(tmp, path)


def sha256_file(path, chunk_size=4 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def iter_int_files(root):
    root = Path(root)
    files = []
    for dirpath, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            if name.lower().endswith('.int'):
                files.append(Path(dirpath) / name)
    return files


def read_upklist(cn_root):
    path = Path(cn_root) / 'Sub_Import' / 'upklist.db'
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    return [line.strip().replace('\\', '/') for line in lines if line.strip()]


def relevant_source_files(en_root, cn_root):
    """返回需要冻结哈希的 ``(side, category, absolute, relative)``。"""
    en_root = Path(en_root).resolve()
    cn_root = Path(cn_root).resolve()
    records = []
    for side, game_root in [('en', en_root), ('cn', cn_root)]:
        int_root = game_root / 'DishonoredGame' / 'Localization' / 'INT'
        for path in iter_int_files(int_root):
            records.append((side, 'int', path, path.relative_to(game_root).as_posix()))

    sub_import = cn_root / 'Sub_Import'
    if sub_import.is_dir():
        for path in sorted(p for p in sub_import.iterdir() if p.is_file()):
            records.append(('cn', 'sub_import', path, path.relative_to(cn_root).as_posix()))

    # 天邈 1.4 分发身份文件：不参与文本提取，但用于证明中文源确实来自该包，
    # 并确保整个 Phase 1 期间安装器/入口脚本/说明也没有被误碰。
    for name in ('DGOTYCNv1.4.exe', 'Sub_Import.bat', '汉化说明.rtf'):
        path = cn_root / name
        if path.exists():
            records.append(('cn', 'package_identity', path, path.relative_to(cn_root).as_posix()))

    for relative in read_upklist(cn_root):
        for side, game_root in [('en', en_root), ('cn', cn_root)]:
            path = game_root.joinpath(*relative.split('/'))
            records.append((side, 'subtitle_upk', path, relative))

    for side, game_root in [('en', en_root), ('cn', cn_root)]:
        cooked = game_root / 'DishonoredGame' / 'CookedPCConsole'
        for path in sorted(cooked.glob('DisFonts*_SF.upk')):
            records.append((side, 'font_upk', path, path.relative_to(game_root).as_posix()))

    # 去重并保持稳定顺序。
    unique = {}
    for record in records:
        unique[(record[0], record[3].casefold())] = record
    return [unique[key] for key in sorted(unique)]


def integrity_snapshot(en_root, cn_root):
    rows = []
    missing = []
    for side, category, path, relative in relevant_source_files(en_root, cn_root):
        if not path.is_file():
            missing.append({'side': side, 'category': category, 'path': relative})
            continue
        stat = path.stat()
        rows.append({
            'side': side,
            'category': category,
            'path': relative,
            'size': stat.st_size,
            'sha256': sha256_file(path),
        })
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, ensure_ascii=False, sort_keys=True).encode('utf-8'))
        digest.update(b'\n')
    return {
        'schema_version': 1,
        'files': rows,
        'missing': missing,
        'file_count': len(rows),
        'total_bytes': sum(row['size'] for row in rows),
        'manifest_sha256': digest.hexdigest(),
    }


def git_info(project_root):
    def run(*args):
        p = subprocess.run(
            ['git', *args], cwd=project_root, capture_output=True,
            text=True, encoding='utf-8', errors='replace', check=False)
        return p.stdout.strip()
    return {
        'head': run('rev-parse', 'HEAD'),
        'status_porcelain': run('status', '--porcelain').splitlines(),
    }


def source_summary(en_root, cn_root, snapshot):
    counts = Counter((row['side'], row['category']) for row in snapshot['files'])
    return {
        'english_root': str(Path(en_root).resolve()),
        'chinese_root': str(Path(cn_root).resolve()),
        'counts': {
            f'{side}_{category}': count
            for (side, category), count in sorted(counts.items())
        },
        'upklist_entries': len(read_upklist(cn_root)),
        'missing': snapshot['missing'],
        'integrity_manifest_sha256': snapshot['manifest_sha256'],
    }


def int_inventory(side, root):
    root = Path(root)
    rows = []
    all_entries = []
    for path in iter_int_files(root):
        raw = path.read_bytes()
        _text, format_name = parse_int.decode_int_bytes(raw)
        entries = parse_int.parse_int_file(path, root=root)
        styles = Counter(entry['style'] for entry in entries)
        rows.append({
            'side': side,
            'file': path.relative_to(root).as_posix(),
            'size': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(),
            'encoding': format_name,
            'entry_count': len(entries),
            'nonempty_count': sum(bool(entry['value']) for entry in entries),
            'styles': dict(sorted(styles.items())),
        })
        all_entries.extend(entries)
    return rows, all_entries


def canonical_identifier(text):
    text = unicodedata.normalize('NFKC', text or '')
    return text.translate(str.maketrans({'。': '.', '：': ':', '／': '/'})).casefold()


def canonical_identity(file_name, entry):
    return (
        canonical_identifier(file_name),
        canonical_identifier(entry.get('section', '')),
        canonical_identifier(entry.get('key', '')),
        int(entry.get('assignment_occurrence', 0)),
        canonical_identifier(entry.get('subkey', '')),
        int(entry.get('field_occurrence', 0)),
    )


def entry_context(entry):
    return {
        'file': entry['file'],
        'section': entry['section'],
        'key': entry['key'],
        'assignment_occurrence': entry['assignment_occurrence'],
        'subkey': entry['subkey'],
        'field_occurrence': entry['field_occurrence'],
        'style': entry['style'],
        'line': entry['line'],
    }


def extract_tags(text):
    import re
    return re.findall(r'<[^>]*>|`[^`]+`|\\[rnt]', text or '')


def text_domain(file_name, entry):
    lower = file_name.casefold()
    if 'dlc05' in lower:
        release = 'dunwall_city_trials'
    elif 'dlc06' in lower:
        release = 'knife_of_dunwall'
    elif 'dlc07' in lower:
        release = 'brigmore_witches'
    else:
        release = 'base_game'
    long_markers = ('note', 'written', 'audiograph', 'chapter', 'journal', 'letter')
    long_text = any(marker in lower for marker in long_markers) or len(entry.get('value', '')) >= 240
    return {'release': release, 'long_text': long_text}


def alignment_id(file_name, source_entry):
    selector = parse_int.entry_selector(source_entry)
    return f"int:{file_name}:{source_entry['section']}:{selector}"


def align_int(en_entries, cn_entries):
    def index(entries):
        result = {}
        for entry in entries:
            key = (entry['file'],) + parse_int.entry_identity(entry)
            if key in result:
                raise ValueError(f'重复 INT identity: {key}')
            result[key] = entry
        return result

    en = index(en_entries)
    cn = index(cn_entries)
    exact_keys = sorted(set(en) & set(cn))
    pairs = [(en[key], cn[key], 'exact') for key in exact_keys]
    en_left = {key: en[key] for key in set(en) - set(cn)}
    cn_left = {key: cn[key] for key in set(cn) - set(en)}

    en_norm = defaultdict(list)
    cn_norm = defaultdict(list)
    for entry in en_left.values():
        en_norm[canonical_identity(entry['file'], entry)].append(entry)
    for entry in cn_left.values():
        cn_norm[canonical_identity(entry['file'], entry)].append(entry)

    normalized_pairs = []
    for key in sorted(set(en_norm) & set(cn_norm)):
        if len(en_norm[key]) == 1 and len(cn_norm[key]) == 1:
            e, c = en_norm[key][0], cn_norm[key][0]
            normalized_pairs.append((e, c, 'normalized_identifier'))
            en_left.pop((e['file'],) + parse_int.entry_identity(e), None)
            cn_left.pop((c['file'],) + parse_int.entry_identity(c), None)
    pairs.extend(normalized_pairs)

    rows = []
    mutations = []
    for source, target, match_kind in sorted(
            pairs, key=lambda pair: alignment_id(pair[0]['file'], pair[0])):
        rid = alignment_id(source['file'], source)
        if match_kind != 'exact':
            mutations.append({
                'id': rid,
                'english_context': entry_context(source),
                'chinese_context': entry_context(target),
                'match_kind': match_kind,
            })
        rows.append({
            'id': rid,
            'layer': 'int',
            'context': entry_context(target),
            'source_context': entry_context(source),
            'domain': text_domain(source['file'], source),
            'en': source['value'],
            'cn': target['value'],
            'tags': extract_tags(target['value']),
            'status': 'aligned' if match_kind == 'exact' else 'aligned_normalized',
        })
    for source in sorted(en_left.values(), key=lambda e: alignment_id(e['file'], e)):
        rows.append({
            'id': alignment_id(source['file'], source),
            'layer': 'int',
            'context': entry_context(source),
            'source_context': entry_context(source),
            'domain': text_domain(source['file'], source),
            'en': source['value'],
            'cn': '',
            'tags': extract_tags(source['value']),
            'status': 'en_only',
        })
    for target in sorted(cn_left.values(), key=lambda e: alignment_id(e['file'], e)):
        rows.append({
            'id': alignment_id(target['file'], target) + ':cn_only',
            'layer': 'int',
            'context': entry_context(target),
            'source_context': {},
            'domain': text_domain(target['file'], target),
            'en': '',
            'cn': target['value'],
            'tags': extract_tags(target['value']),
            'status': 'cn_only',
        })
    ids = Counter(row['id'] for row in rows)
    duplicate_ids = sorted(rid for rid, count in ids.items() if count > 1)
    return rows, mutations, list(en_left.values()), list(cn_left.values()), duplicate_ids


def issue_entry(entry):
    return {
        'context': entry_context(entry),
        'selector': parse_int.entry_selector(entry),
        'value': entry['value'],
    }


def write_sample_csv(path, aligned_rows, count=50):
    """稳定分层抽样；人工结论列留空。"""
    candidates = [r for r in aligned_rows if r['status'].startswith('aligned') and (r['en'] or r['cn'])]
    buckets = {
        'base_game': [r for r in candidates if r['domain']['release'] == 'base_game'],
        'dunwall_city_trials': [r for r in candidates if r['domain']['release'] == 'dunwall_city_trials'],
        'knife_of_dunwall': [r for r in candidates if r['domain']['release'] == 'knife_of_dunwall'],
        'brigmore_witches': [r for r in candidates if r['domain']['release'] == 'brigmore_witches'],
        'long_text': [r for r in candidates if r['domain']['long_text']],
        'structured': [r for r in candidates if r['context']['style'] == 'struct_field'],
    }
    chosen = {}
    quotas = {
        'base_game': 10,
        'dunwall_city_trials': 8,
        'knife_of_dunwall': 8,
        'brigmore_witches': 8,
        'long_text': 8,
        'structured': 8,
    }
    for bucket, quota in quotas.items():
        ranked = sorted(
            buckets[bucket],
            key=lambda row: hashlib.sha256((bucket + '\0' + row['id']).encode()).hexdigest())
        for row in ranked:
            chosen.setdefault(row['id'], (bucket, row))
            if sum(1 for b, _r in chosen.values() if b == bucket) >= quota:
                break
    if len(chosen) < count:
        ranked = sorted(candidates, key=lambda row: hashlib.sha256(row['id'].encode()).hexdigest())
        for row in ranked:
            chosen.setdefault(row['id'], ('fill', row))
            if len(chosen) >= count:
                break
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'sample_group', 'id', 'release', 'file', 'section', 'selector',
            'en', 'cn', 'alignment_ok', 'note'])
        writer.writeheader()
        for _rid, (bucket, row) in sorted(chosen.items()):
            writer.writerow({
                'sample_group': bucket,
                'id': row['id'],
                'release': row['domain']['release'],
                'file': row['context']['file'],
                'section': row['context']['section'],
                'selector': parse_int.entry_selector(row['context']),
                'en': row['en'],
                'cn': row['cn'],
                'alignment_ok': '',
                'note': '',
            })
    return len(chosen)


def run_initial(args):
    project = Path(args.project_root).resolve()
    raw = project / 'data' / 'raw'
    aligned = project / 'data' / 'aligned'
    manifests = raw / 'manifests'
    started = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()

    print('生成源文件 SHA-256 基线（只读）...')
    snapshot = integrity_snapshot(args.en_root, args.cn_root)
    json_write(manifests / 'source_integrity_before.json', snapshot)
    json_write(manifests / 'source_summary.json', source_summary(
        args.en_root, args.cn_root, snapshot))
    json_write(manifests / 'phase1_run.json', {
        'schema_version': 1,
        'started_at': started,
        'python': sys.version,
        'platform': platform.platform(),
        'project_root': str(project),
        'english_root': str(Path(args.en_root).resolve()),
        'chinese_root': str(Path(args.cn_root).resolve()),
        'git': git_info(project),
        'tool_sha256': sha256_file(Path(__file__)),
    })
    if snapshot['missing']:
        raise SystemExit(f"相关源文件缺失 {len(snapshot['missing'])} 个，见 source_integrity_before.json")

    print('解析 658+658 个 INT 文件...')
    en_int_root = Path(args.en_root) / 'DishonoredGame' / 'Localization' / 'INT'
    cn_int_root = Path(args.cn_root) / 'DishonoredGame' / 'Localization' / 'INT'
    en_inventory, en_entries = int_inventory('en', en_int_root)
    cn_inventory, cn_entries = int_inventory('cn', cn_int_root)
    json_write(raw / 'int_file_inventory.json', en_inventory + cn_inventory)

    rows, mutations, en_only, cn_only, duplicate_ids = align_int(en_entries, cn_entries)
    jsonl_write(aligned / 'int_corpus.jsonl', rows)
    issues = {
        'normalized_identifier_matches': mutations,
        'en_only': [issue_entry(entry) for entry in en_only],
        'cn_only': [issue_entry(entry) for entry in cn_only],
        'duplicate_ids': duplicate_ids,
    }
    json_write(aligned / 'int_alignment_issues.json', issues)

    status_counts = Counter(row['status'] for row in rows)
    release_counts = Counter(row['domain']['release'] for row in rows)
    style_counts = Counter(row['context']['style'] for row in rows)
    coverage = {
        'physical_files': {'en': len(en_inventory), 'cn': len(cn_inventory)},
        'files_with_entries': {
            'en': sum(row['entry_count'] > 0 for row in en_inventory),
            'cn': sum(row['entry_count'] > 0 for row in cn_inventory),
        },
        'entries': {'en': len(en_entries), 'cn': len(cn_entries), 'corpus_rows': len(rows)},
        'nonempty_entries': {
            'en': sum(bool(entry['value']) for entry in en_entries),
            'cn': sum(bool(entry['value']) for entry in cn_entries),
        },
        'status': dict(sorted(status_counts.items())),
        'release': dict(sorted(release_counts.items())),
        'target_styles': dict(sorted(style_counts.items())),
        'normalized_identifier_matches': len(mutations),
        'duplicate_ids': duplicate_ids,
    }
    json_write(aligned / 'int_coverage.json', coverage)
    json_write(raw / 'int_parse_stats.json', {
        'english': {
            'entries': len(en_entries),
            'styles': dict(sorted(Counter(e['style'] for e in en_entries).items())),
            'duplicate_identities': 0,
        },
        'chinese': {
            'entries': len(cn_entries),
            'styles': dict(sorted(Counter(e['style'] for e in cn_entries).items())),
            'duplicate_identities': 0,
        },
        'corpus_duplicate_ids': duplicate_ids,
    })
    sample_count = write_sample_csv(aligned / 'int_sample_review.csv', rows)
    print(json.dumps(coverage, ensure_ascii=False, indent=1))
    print(f'INT 抽样表: {sample_count} 条')
    if duplicate_ids:
        raise SystemExit(f'INT corpus 存在重复 ID: {len(duplicate_ids)}')


def run_after(args):
    project = Path(args.project_root).resolve()
    manifests = project / 'data' / 'raw' / 'manifests'
    before_path = manifests / 'source_integrity_before.json'
    if not before_path.exists():
        raise SystemExit('缺少 source_integrity_before.json')
    before = json.load(open(before_path, encoding='utf-8'))
    after = integrity_snapshot(args.en_root, args.cn_root)
    json_write(manifests / 'source_integrity_after.json', after)
    same = before['manifest_sha256'] == after['manifest_sha256'] and not after['missing']
    json_write(manifests / 'source_integrity_comparison.json', {
        'same': same,
        'before_manifest_sha256': before['manifest_sha256'],
        'after_manifest_sha256': after['manifest_sha256'],
        'before_file_count': before['file_count'],
        'after_file_count': after['file_count'],
    })
    print('源目录完整性:', '一致' if same else '发生变化')
    if not same:
        raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--en-root', required=True)
    ap.add_argument('--cn-root', required=True)
    ap.add_argument('--project-root', default=os.path.dirname(os.path.dirname(__file__)))
    ap.add_argument('--after', action='store_true', help='生成执行后快照并与 before 比较')
    args = ap.parse_args()
    if args.after:
        run_after(args)
    else:
        run_initial(args)


if __name__ == '__main__':
    main()
