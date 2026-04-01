#!/usr/bin/env python3
"""
飞书多维表格同步脚本 v2
======================
将评测结果同步到飞书多维表格 (Base)

字段映射（与飞书试标集结构一致）:
- 编号
- 类目
- 难度
- 重点测试点
- 提示词
- 检查点
- 模型
- 是否含文字元素
- 提示词理解（✖️3）
- 合理性（✖️3）
- 图像质量（✖️2）
- 文字渲染（✖️2）
- 美观度（✖️2）
- 加权总分
- 错误类型
- 标注备注

使用前确保已安装 lark-cli 并完成认证:
  lark-cli auth login
"""

import os
import json
import csv
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict

def run_lark_cli(args: List[str], input_data: str = None) -> Dict:
    """执行 lark-cli 命令"""
    cmd = ['lark-cli'] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_data
    )

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return {'ok': False, 'error': result.stderr}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {'ok': True, 'raw': result.stdout}


def read_csv_data(csv_path: str) -> List[Dict]:
    """读取 CSV 数据"""
    records = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    return records


def create_evaluation_base(name: str = "图像模型评测结果") -> str:
    """创建新的多维表格"""
    result = run_lark_cli([
        'base', '+base-create',
        '--name', name
    ])

    if result.get('ok'):
        base_token = result.get('data', {}).get('app', {}).get('token')
        print(f"创建多维表格成功: {base_token}")
        return base_token
    else:
        print(f"创建失败: {result.get('error')}")
        return None


def create_table_with_fields(base_token: str, table_name: str = "评测结果") -> str:
    """创建数据表并定义字段"""
    fields = [
        {"field_name": "编号", "type": 1},                    # 文本
        {"field_name": "类目", "type": 1},                    # 文本
        {"field_name": "子类|场景方向", "type": 1},           # 文本
        {"field_name": "难度", "type": 1},                    # 文本
        {"field_name": "重点测试点", "type": 1},              # 文本
        {"field_name": "提示词", "type": 1},                  # 文本
        {"field_name": "检查点", "type": 1},                  # 文本
        {"field_name": "模型", "type": 1},                    # 文本
        {"field_name": "是否含文字元素", "type": 1},          # 文本
        {"field_name": "提示词理解（✖️3）", "type": 1},       # 文本（评分用文本，支持N/A）
        {"field_name": "合理性（✖️3）", "type": 1},           # 文本
        {"field_name": "图像质量（✖️2）", "type": 1},         # 文本
        {"field_name": "文字渲染（✖️2）", "type": 1},         # 文本
        {"field_name": "美观度（✖️2）", "type": 1},           # 文本
        {"field_name": "加权总分", "type": 1},                # 文本
        {"field_name": "错误类型", "type": 1},                # 文本
        {"field_name": "标注备注", "type": 1},                # 文本
        {"field_name": "出图轮次", "type": 2},                # 数字
        {"field_name": "复核状态", "type": 1},                # 文本
    ]

    # 创建数据表
    result = run_lark_cli([
        'base', '+table-create',
        '--base-token', base_token,
        '--data', json.dumps({
            "table": {"name": table_name},
            "fields": fields
        })
    ])

    if result.get('ok'):
        table_id = result.get('data', {}).get('table', {}).get('table_id')
        print(f"创建数据表成功: {table_id}")
        return table_id
    else:
        print(f"创建数据表失败: {result.get('error')}")
        return None


def map_csv_to_feishu_fields(csv_row: Dict) -> Dict:
    """将 CSV 字段映射到飞书多维表格字段（更新模式只更新分数字段）"""

    def safe_str(value):
        """安全转换为字符串"""
        if value is None or value == '':
            return ''
        return str(value)

    def format_score(value):
        """格式化分数，None 显示为 N/A"""
        if value is None or value == '':
            return 'N/A'
        return str(value)

    fields = {}

    # 多维度评分（匹配目标表格字段名）
    if csv_row.get('score_prompt') is not None:
        fields['提示词理解(×3)'] = format_score(csv_row['score_prompt'])
    if csv_row.get('score_rationality') is not None:
        fields['合理性(×3)'] = format_score(csv_row['score_rationality'])
    if csv_row.get('score_quality') is not None:
        fields['图像质量(×2)'] = format_score(csv_row['score_quality'])
    if csv_row.get('score_text') is not None:
        fields['文字渲染(×2)'] = format_score(csv_row['score_text'])
    elif csv_row.get('has_text_element') == '否':
        fields['文字渲染(×2)'] = 'N/A'
    if csv_row.get('score_aesthetic') is not None:
        fields['美观度(×2)'] = format_score(csv_row['score_aesthetic'])

    # 加权总分
    if csv_row.get('weighted_total'):
        fields['加权总分'] = format_score(csv_row['weighted_total'])

    # 错误类型
    if csv_row.get('error_types'):
        error_types = csv_row['error_types']
        if isinstance(error_types, list):
            fields['错误类型'] = error_types  # multi-select
        else:
            fields['错误类型'] = safe_str(error_types).split(';')

    # 备注
    if csv_row.get('remarks'):
        fields['题目备注'] = safe_str(csv_row['remarks'])

    # GSB（冲突时标记 ⚠️）
    if csv_row.get('gsb'):
        gsb_value = safe_str(csv_row['gsb'])
        if csv_row.get('gsb_conflict') == True or csv_row.get('gsb_conflict') == 'True':
            gsb_value = f"⚠️ {gsb_value}"
        fields['GSB'] = gsb_value

    return fields


def sync_records(base_token: str, table_id: str, records: List[Dict], batch_size: int = 50):
    """批量同步记录到飞书多维表格"""
    total = len(records)
    synced = 0

    for i in range(0, total, batch_size):
        batch = records[i:i + batch_size]

        # 构建飞书记录格式
        feishu_records = []
        for r in batch:
            fields = map_csv_to_feishu_fields(r)
            if fields:
                feishu_records.append({'fields': fields})

        if not feishu_records:
            continue

        # 调用 lark-cli 批量创建记录
        data = json.dumps({'records': feishu_records})

        result = run_lark_cli([
            'base', '+record-upsert',
            '--base-token', base_token,
            '--table-id', table_id,
            '--data', '@-'
        ], input_data=data)

        if result.get('ok'):
            synced += len(batch)
            print(f"  已同步 {synced}/{total} 条记录")
        else:
            print(f"  同步失败: {result.get('error', 'Unknown error')}")

    return synced


def load_existing_records(base_token: str, table_id: str) -> Dict[str, str]:
    """从飞书表格加载已有记录，建立 编号 -> record_id 映射（处理分页）"""
    record_map = {}
    offset = 0
    page_size = 500

    # 编号字段的 field_id（固定，不会变化）
    # TODO: 替换为你的飞书多维表格"编号"字段的 field_id
    ID_FIELD_ID = 'YOUR_ID_FIELD_ID'

    while True:
        result = run_lark_cli([
            'base', '+record-list',
            '--base-token', base_token,
            '--table-id', table_id,
            '--limit', str(page_size),
            '--offset', str(offset)
        ])

        if not result.get('ok'):
            print(f"加载记录失败: {result.get('error')}")
            break

        data = result.get('data', {})
        field_ids = data.get('field_id_list', [])
        records = data.get('data', [])
        record_ids = data.get('record_id_list', [])

        # 每页都用 field_id 定位编号字段索引（字段顺序可能变化）
        if ID_FIELD_ID in field_ids:
            id_idx = field_ids.index(ID_FIELD_ID)
        else:
            print(f"找不到编号字段 (field_id: {ID_FIELD_ID})")
            break

        for i, record_data in enumerate(records):
            record_id = record_ids[i] if i < len(record_ids) else None
            sample_id = record_data[id_idx] if id_idx < len(record_data) else None
            if sample_id and record_id:
                record_map[sample_id] = record_id

        offset += len(records)
        print(f"  已加载 {len(record_map)} 条记录...")

        if not data.get('has_more', False):
            break

    return record_map


def update_record(base_token: str, table_id: str, record_id: str, fields: Dict) -> bool:
    """更新单条记录"""
    result = run_lark_cli([
        'base', '+record-upsert',
        '--base-token', base_token,
        '--table-id', table_id,
        '--record-id', record_id,
        '--json', json.dumps(fields)
    ])
    return result.get('ok', False)


def sync_update_records(base_token: str, table_id: str, records: List[Dict]):
    """按编号匹配更新已有记录"""
    # 加载已有记录
    print("正在加载飞书表格已有记录...")
    record_map = load_existing_records(base_token, table_id)
    print(f"找到 {len(record_map)} 条已有记录")

    updated = 0
    not_found = 0

    for r in records:
        sample_id = r.get('sample_id', '')
        if not sample_id:
            continue

        if sample_id not in record_map:
            not_found += 1
            continue

        record_id = record_map[sample_id]
        fields = map_csv_to_feishu_fields(r)

        if update_record(base_token, table_id, record_id, fields):
            updated += 1
            if updated % 10 == 0:
                print(f"  已更新 {updated} 条记录")

    print(f"\n更新完成!")
    print(f"  成功更新: {updated} 条")
    print(f"  未找到匹配: {not_found} 条")
    return updated


def main():
    parser = argparse.ArgumentParser(description='同步评测结果到飞书多维表格')
    parser.add_argument('--data', '-d', required=True, help='评测结果 CSV 或 JSON 文件')
    parser.add_argument('--base', '-b', required=True, help='多维表格 app_token')
    parser.add_argument('--table', '-t', required=True, help='数据表 table_id')
    parser.add_argument('--update', action='store_true', help='更新模式：按编号匹配更新已有记录')
    parser.add_argument('--create', action='store_true', help='创建模式：新增记录')
    parser.add_argument('--name', '-n', default='图像模型评测结果', help='新多维表格名称')

    args = parser.parse_args()

    # 检查数据文件
    if not os.path.exists(args.data):
        print(f"错误: 数据文件不存在 {args.data}")
        return

    # 读取数据
    print(f"正在读取数据: {args.data}")
    if args.data.endswith('.json'):
        with open(args.data, 'r', encoding='utf-8') as f:
            records = json.load(f)
    else:
        records = read_csv_data(args.data)
    print(f"共 {len(records)} 条记录")

    if not records:
        print("没有数据需要同步")
        return

    base_token = args.base
    table_id = args.table

    # 更新模式
    if args.update:
        sync_update_records(base_token, table_id, records)
    else:
        # 新增模式
        print("正在同步记录...")
        synced = sync_records(base_token, table_id, records)
        print(f"\n同步完成! 共同步 {synced} 条记录")

    print(f"多维表格: https://feishu.cn/base/{base_token}")

if __name__ == '__main__':
    main()
