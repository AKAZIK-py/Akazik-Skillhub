#!/usr/bin/env python3
"""
标注结果收集脚本 v4 (支持 0,1,2 三分制)
=======================================
从百度千帆平台导出的标注结果中提取评分数据。
支持 GSB 整体比较判断。

评分维度（加权）：
- 提示词理解 ×3
- 合理性 ×3
- 图像质量 ×2
- 文字渲染 ×2
- 美观度 ×2
"""

import os
import json
import re
import csv
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# ============================================
# 评分权重配置
# ============================================
SCORE_WEIGHTS = {
    '提示词理解': 3,
    '合理性': 3,
    '图像质量': 2,
    '文字渲染': 2,
    '美观度': 2,
}


def load_blind_key(input_dir: str) -> Dict:
    """加载盲测密钥"""
    blind_key_path = Path(input_dir) / "blind_key.json"
    if blind_key_path.exists():
        with open(blind_key_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def parse_score(text: str, dimension: str) -> Optional[int]:
    """从文本中提取特定维度的分数（0/1/2）

    支持多种格式：忽略所有横线，提取数字
    - 提示词理解: 2分
    - 提示词理解: _2_
    - 提示词理解: __2__
    - 提示词理解: __1_分 (0/1/2)
    - 提示词理解: N/A
    """
    # 匹配维度后的内容
    match = re.search(rf'{dimension}[：:]\s*(.+?)(?=\n|$)', text)
    if not match:
        return None

    value = match.group(1).strip()

    # 检查 N/A
    if 'N/A' in value.upper():
        return None

    # 去掉所有横线、空格、分字，以及括号内容
    value = value.replace('_', '').replace(' ', '').replace('分', '')
    # 去掉括号及其内容，如 (0/1/2)
    value = re.sub(r'\(.*?\)', '', value)

    # 提取第一个数字
    match_num = re.search(r'(\d)', value)
    if match_num:
        score = int(match_num.group(1))
        if 0 <= score <= 2:
            return score

    return None


def parse_all_scores(text: str) -> Dict[str, Optional[int]]:
    """解析所有维度的分数"""
    scores = {}
    for dimension in SCORE_WEIGHTS.keys():
        scores[dimension] = parse_score(text, dimension)
    return scores


def calculate_weighted_total(scores: Dict[str, Optional[int]]) -> Tuple[float, int]:
    """计算加权总分"""
    total_score = 0
    total_weight = 0

    for dimension, score in scores.items():
        if score is not None:
            weight = SCORE_WEIGHTS.get(dimension, 1)
            total_score += score * weight
            total_weight += weight

    if total_weight == 0:
        return 0, 0

    return round(total_score / total_weight, 2), total_weight


def parse_error_types(text: str) -> List[str]:
    """从文本中提取错误类型（支持序号格式），忽略横线

    空值时默认返回 ['无明显错误']
    """
    error_map = {
        '1': '跑题/主体错误',
        '2': '关键属性错误',
        '3': '数量错误',
        '4': '位置关系错误',
        '5': '否定指令未执行',
        '6': '文字错误',
        '7': '人体/结构异常',
        '8': '光影/反射不合理',
        '9': '多余元素干扰',
        '10': '清晰度/细节不足',
        '11': '无明显错误',
    }

    error_types = []

    # 匹配错误类型序号
    match = re.search(r'错误类型序号[：:]\s*(.+?)(?=\n|备注|$)', text)
    if match:
        numbers_str = match.group(1).strip()
        # 去掉所有横线
        numbers_str = numbers_str.replace('_', '')
        # 解析逗号或顿号分隔的数字
        numbers = re.findall(r'\d+', numbers_str)
        for num in numbers:
            if num in error_map:
                error_type = error_map[num]
                if error_type not in error_types:
                    error_types.append(error_type)

    # 空值时默认返回无明显错误
    if not error_types:
        return ['无明显错误']

    return error_types


def parse_remarks(text: str) -> str:
    """从文本中提取备注，去掉横线"""
    match = re.search(r'备注[：:]\s*(.+?)(?=\n|$)', text)
    if match:
        value = match.group(1).strip()
        # 去掉前后横线
        value = value.strip('_')
        return value
    return ''


def parse_gsb(text: str) -> Optional[str]:
    """从文本中提取 GSB 判断

    支持多种格式：
    - GSB判断: G
    - 备注下一行写 G/S/B（可能隔空行）
    """
    # 方式1: 标准 GSB判断字段
    match = re.search(r'GSB判断[：:]\s*_*([GSB])_*', text)
    if match:
        return match.group(1)

    # 方式2: 备注后（可能隔空行）写 G/S/B
    # 匹配 "备注: xxx\n\nG" 或 "备注: ___\nG" 等格式
    match = re.search(r'备注[：:][^\n]*\n(?:\s*\n)*\s*_*([GSB])_*\s*(?:\n|$)', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    # 方式3: 文末单独一行 G/S/B
    lines = text.strip().split('\n')
    for line in reversed(lines[-5:]):  # 只检查最后5行
        line = line.strip().replace('_', '').replace(' ', '')
        if line in ['G', 'S', 'B', 'g', 's', 'b']:
            return line.upper()

    return None


def parse_gsb_reason(text: str) -> str:
    """从文本中提取 GSB 理由"""
    match = re.search(r'GSB理由[：:]\s*(.+?)(?=\n|$)', text)
    if match:
        return match.group(1).strip()
    return ''


def parse_sample_id(text: str) -> str:
    """从文本中提取样本编号"""
    match = re.search(r'样本编号[：:]\s*(\S+)', text)
    if match:
        return match.group(1)
    return ''


def parse_category(text: str) -> str:
    """从文本中提取类目"""
    match = re.search(r'类目[：:]\s*(.+?)(?=\n|$)', text)
    if match:
        return match.group(1).strip()
    return ''


def parse_difficulty(text: str) -> str:
    """从文本中提取难度"""
    match = re.search(r'难度[：:]\s*(.+?)(?=\n|$)', text)
    if match:
        return match.group(1).strip()
    return ''


def parse_test_focus(text: str) -> str:
    """从文本中提取重点测试点"""
    match = re.search(r'重点测试点[：:]\s*(.+?)(?=\n|$)', text)
    if match:
        return match.group(1).strip()
    return ''


def parse_has_text_element(text: str) -> str:
    """从文本中提取是否含文字元素"""
    match = re.search(r'是否含文字元素[：:]\s*(.+?)(?=\n|$)', text)
    if match:
        return match.group(1).strip()
    return '否'


def parse_checklist(text: str) -> str:
    """从文本中提取检查点"""
    match = re.search(r'【检查点】\s*(.+?)(?=\n\n|============================================|$)', text, re.DOTALL)
    if match:
        return match.group(1).strip().replace('\n', '')
    return ''


def parse_annotated_json(json_path: Path, blind_key: Dict) -> Dict:
    """解析单个标注 JSON 文件"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    prompt_text = data.get('prompt', '')
    metadata = data.get('metadata', {})

    file_index = metadata.get('file_index', json_path.stem)

    # 优先从 metadata 获取，没有则从 prompt 文本解析
    sample_id = metadata.get('sample_id', '') or parse_sample_id(prompt_text)
    model_code = metadata.get('model_code', '')
    real_model = metadata.get('_real_model', '')

    # 从 prompt 文本解析基本信息
    category = parse_category(prompt_text)
    difficulty = parse_difficulty(prompt_text)
    test_focus = parse_test_focus(prompt_text)
    has_text_element = parse_has_text_element(prompt_text)
    checklist = parse_checklist(prompt_text)
    real_model = metadata.get('_real_model', '')

    if not real_model and blind_key:
        file_mapping = blind_key.get('file_mapping', {})
        if str(file_index) in file_mapping:
            info = file_mapping[str(file_index)]
            model_code = info.get('model_code', '')
            real_model = info.get('real_model', '')

    scores = parse_all_scores(prompt_text)
    weighted_total, total_weight = calculate_weighted_total(scores)
    error_types = parse_error_types(prompt_text)
    remarks = parse_remarks(prompt_text)
    gsb = parse_gsb(prompt_text)
    gsb_reason = parse_gsb_reason(prompt_text)

    return {
        'file_index': file_index,
        'sample_id': sample_id,
        'model_code': model_code,
        'real_model': real_model,
        'original_prompt': metadata.get('original_prompt', ''),
        'checklist': metadata.get('checklist', '') or checklist,
        'difficulty': metadata.get('difficulty', '') or difficulty,
        'category': metadata.get('category', '') or category,
        'test_focus': metadata.get('test_focus', '') or test_focus,
        'has_text_element': metadata.get('has_text_element', has_text_element),

        'score_prompt': scores.get('提示词理解'),
        'score_rationality': scores.get('合理性'),
        'score_quality': scores.get('图像质量'),
        'score_text': scores.get('文字渲染'),
        'score_aesthetic': scores.get('美观度'),

        'weighted_total': weighted_total,
        'total_weight': total_weight,
        'error_types': error_types,
        'remarks': remarks,
        'gsb': gsb,
        'gsb_reason': gsb_reason,
    }


def collect_annotations(input_dir: str) -> List[Dict]:
    """收集所有标注结果"""
    input_path = Path(input_dir)
    blind_key = load_blind_key(input_dir)

    if blind_key:
        print("已加载盲测密钥，将解码模型身份")

    results = []
    json_files = [f for f in input_path.glob('*.json')
                  if f.name not in ['index.json', 'blind_key.json', 'summary.json', 'annotations.json']]

    for json_file in sorted(json_files, key=lambda x: int(x.stem) if x.stem.isdigit() else 0):
        result = parse_annotated_json(json_file, blind_key)
        results.append(result)

    return results


def collect_gsb_results(results: List[Dict]) -> Dict[str, Dict]:
    """收集标注人员填写的 GSB 结果

    GSB 处理规则：
    1. GSB 保留在各自图上（A 图的 GSB 在 A 记录，B 图的 GSB 在 B 记录）
    2. 如果 A 图和 B 图都有 GSB 且不同，标记冲突
    """
    # 按基础样本编号分组（去掉 -A/-B 后缀）
    samples = {}
    for r in results:
        sample_id = r['sample_id']
        # 提取基础编号：A-017-A -> A-017
        base_id = sample_id.rsplit('-', 1)[0] if '-' in sample_id else sample_id
        suffix = sample_id.rsplit('-', 1)[1] if '-' in sample_id else ''

        if base_id not in samples:
            samples[base_id] = {}

        # 确定模型编号 (A 或 B)
        model_code = r['model_code']
        if not model_code:
            if sample_id.endswith('-A') or suffix == 'A':
                model_code = 'A'
            elif sample_id.endswith('-B') or suffix == 'B':
                model_code = 'B'

        samples[base_id][model_code] = r

    gsb_results = {}
    for base_id, models in samples.items():
        if 'A' in models and 'B' in models:
            gsb_a = models['A'].get('gsb')
            gsb_b = models['B'].get('gsb')
            gsb_reason_a = models['A'].get('gsb_reason', '')
            gsb_reason_b = models['B'].get('gsb_reason', '')

            # 检测冲突：两边都有 GSB 但不同
            has_conflict = False
            if gsb_a and gsb_b and gsb_a != gsb_b:
                has_conflict = True
                models['A']['gsb_conflict'] = True
                models['B']['gsb_conflict'] = True

            # 记录配对信息（用于统计）
            gsb_results[base_id] = {
                'gsb_a': gsb_a,
                'gsb_b': gsb_b,
                'gsb_reason_a': gsb_reason_a,
                'gsb_reason_b': gsb_reason_b,
                'has_conflict': has_conflict,
                'score_a': models['A']['weighted_total'],
                'score_b': models['B']['weighted_total'],
                'model_a': models['A']['real_model'],
                'model_b': models['B']['real_model']
            }

    return gsb_results


def generate_summary(results: List[Dict]) -> Dict:
    """生成汇总统计"""
    total = len(results)
    scored = [r for r in results if r['weighted_total'] > 0]

    weighted_scores = [r['weighted_total'] for r in scored]
    avg_score = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0

    # 按模型统计
    model_results = {}
    for r in scored:
        model = r.get('real_model') or r.get('model_code', 'Unknown')
        if model not in model_results:
            model_results[model] = []
        model_results[model].append(r)

    model_stats = {}
    for model, model_data in model_results.items():
        scores = [r['weighted_total'] for r in model_data]
        model_stats[model] = {
            'count': len(model_data),
            'avg_score': round(sum(scores) / len(scores), 2),
            'total_score': sum(scores)
        }

    # 各维度平均分
    dimension_avgs = {}
    dim_key_map = {
        '提示词理解': 'score_prompt',
        '合理性': 'score_rationality',
        '图像质量': 'score_quality',
        '文字渲染': 'score_text',
        '美观度': 'score_aesthetic'
    }
    for dim, key in dim_key_map.items():
        values = [r[key] for r in scored if r[key] is not None]
        dimension_avgs[dim] = round(sum(values) / len(values), 2) if values else 0

    # 错误类型统计
    error_counts = {}
    for r in scored:
        for error in r['error_types']:
            error_counts[error] = error_counts.get(error, 0) + 1

    # GSB 统计（从标注结果收集）
    gsb_results = collect_gsb_results(results)
    gsb_counts = {'G': 0, 'S': 0, 'B': 0, 'conflict': 0}
    for gsb_data in gsb_results.values():
        if gsb_data.get('has_conflict'):
            gsb_counts['conflict'] += 1
        # 分别统计 A 图和 B 图的 GSB
        if gsb_data.get('gsb_a') in gsb_counts:
            gsb_counts[gsb_data['gsb_a']] += 1
        elif gsb_data.get('gsb_b') in gsb_counts:
            # 如果 A 图没写但 B 图写了
            gsb_counts[gsb_data['gsb_b']] += 1

    return {
        'total_samples': total,
        'scored_samples': len(scored),
        'average_weighted_score': round(avg_score, 2),
        'model_stats': model_stats,
        'dimension_averages': dimension_avgs,
        'error_distribution': dict(sorted(error_counts.items(), key=lambda x: -x[1])),
        'gsb_summary': gsb_counts,
        'gsb_details': gsb_results,
        'collected_at': datetime.now().isoformat()
    }


def export_to_csv(results: List[Dict], output_path: Path):
    """导出为 CSV"""
    fieldnames = [
        'file_index', 'sample_id', 'model_code', 'real_model',
        'category', 'difficulty', 'test_focus',
        'original_prompt', 'checklist', 'has_text_element',
        'score_prompt', 'score_rationality', 'score_quality', 'score_text', 'score_aesthetic',
        'weighted_total', 'error_types', 'remarks', 'gsb', 'gsb_reason', 'gsb_conflict'
    ]

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()

        for r in results:
            row = r.copy()
            row['error_types'] = ';'.join(r['error_types'])
            for key in row:
                if row[key] is None:
                    row[key] = ''
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description='收集标注结果（0,1,2三分制）')
    parser.add_argument('--input', '-i', required=True, help='标注结果输入目录')
    parser.add_argument('--output', '-o', default='./results', help='输出目录')

    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    print("正在收集标注结果...")
    results = collect_annotations(args.input)

    print("正在生成汇总统计...")
    summary = generate_summary(results)

    with open(output_path / 'annotations.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    with open(output_path / 'summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    export_to_csv(results, output_path / 'feishu_import.csv')

    # 打印汇总
    print("\n" + "="*60)
    print("标注结果汇总")
    print("="*60)
    print(f"总样本数: {summary['total_samples']}")

    print(f"\n按模型统计:")
    for model, stats in summary['model_stats'].items():
        print(f"  {model}: 平均分 {stats['avg_score']}, 总分 {stats['total_score']}")

    print(f"\nGSB 统计:")
    print(f"  G (A胜): {summary['gsb_summary']['G']}")
    print(f"  S (持平): {summary['gsb_summary']['S']}")
    print(f"  B (B胜): {summary['gsb_summary']['B']}")
    if summary['gsb_summary']['conflict'] > 0:
        print(f"  ⚠️ 冲突: {summary['gsb_summary']['conflict']} (需质检处理)")

    print(f"\n输出文件:")
    print(f"  - {output_path / 'annotations.json'}")
    print(f"  - {output_path / 'summary.json'}")
    print(f"  - {output_path / 'feishu_import.csv'}")


if __name__ == '__main__':
    main()
