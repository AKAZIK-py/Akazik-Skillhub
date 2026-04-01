#!/usr/bin/env python3
"""
评测数据准备脚本 v6 (A/B盲测版 - 0,1,2三分制)
================================================
符合百度千帆平台上传要求：
- 文件从 0 开始命名
- 同一样本的 A/B 图片相邻（便于 GSB 比较）
- 评分采用 0, 1,2 三分制

模型映射:
- Model A → model-a
- Model B → model-b
"""

import os
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from PIL import Image

# ============================================
# 模型映射配置（盲测用）
# 请根据实际评测的模型修改此配置
# ============================================
MODEL_MAP = {
    "model-a": "A",
    "model-b": "B",
}

MODEL_DECODE = {v: k for k, v in MODEL_MAP.items()}

FEISHU_MODEL_MAP = {
    "ModelA": "model-a",
    "ModelB": "model-b",
}

# ============================================
# 评分模板（0,1,2三分制）
# A图（偶数编号）：只打维度分
# B图（奇数编号）：打维度分 + GSB对比
# ============================================

EVAL_TEMPLATE_A = """【评测任务】请对这张图片进行多维度评分（0/1/2分制）

============================================
【基本信息】
样本编号: {sample_id}
类目: {category}
难度: {difficulty}
重点测试点: {test_focus}
是否含文字元素: {has_text}

============================================
【提示词】
{prompt}

============================================
【检查点】
{checklist}

============================================
【请填写评分】（每项打 0、1 或 2 分）
提示词理解: ___分 (0/1/2)
合理性: ___分 (0/1/2)
图像质量: ___分 (0/1/2)
{text_score_line}
美观度: ___分 (0/1/2)

【错误类型】（多选，填写错误类型序号，如 1,3,5）
1.跑题/主体错误  2.关键属性错误  3.数量错误  4.位置关系错误
5.否定指令未执行  6.文字错误  7.人体/结构异常  8.光影/反射不合理
9.多余元素干扰  10.清晰度/细节不足  11.无明显错误

错误类型序号: ___

备注: ___
"""

EVAL_TEMPLATE_B = """【评测任务】请对这张图片进行多维度评分（0/1/2分制）

============================================
【基本信息】
样本编号: {sample_id}
类目: {category}
难度: {difficulty}
重点测试点: {test_focus}
是否含文字元素: {has_text}

============================================
【提示词】
{prompt}

============================================
【检查点】
{checklist}

============================================
【请填写评分】（每项打 0、1 或 2 分）
提示词理解: ___分 (0/1/2)
合理性: ___分 (0/1/2)
图像质量: ___分 (0/1/2)
{text_score_line}
美观度: ___分 (0/1/2)

【错误类型】（多选，填写错误类型序号，如 1,3,5）
1.跑题/主体错误  2.关键属性错误  3.数量错误  4.位置关系错误
5.否定指令未执行  6.文字错误  7.人体/结构异常  8.光影/反射不合理
9.多余元素干扰  10.清晰度/细节不足  11.无明显错误

错误类型序号: ___

备注: ___

============================================
【GSB整体对比】（本图与前一张图对比）
说明: 请对比本图(B)与前一张图(A)，判断整体优劣
   G: A图整体优于B图
   S: 两图整体相当
   B: B图整体优于A图

GSB判断: ___ (G/S/B)
GSB理由: ___
"""


def run_lark_cli(args: List[str]) -> Dict:
    """执行 lark-cli 命令"""
    result = subprocess.run(
        ['lark-cli'] + args,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        return {'ok': False, 'error': result.stderr}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {'ok': True, 'raw': result.stdout}


def load_feishu_data(base_token: str, table_id: str) -> List[Dict]:
    """从飞书多维表格加载所有数据（处理分页）"""
    all_records = []
    offset = 0
    page_size = 500

    while True:
        result = run_lark_cli([
            'base', '+record-list',
            '--base-token', base_token,
            '--table-id', table_id,
            '--limit', str(page_size),
            '--offset', str(offset)
        ])
        if not result.get('ok'):
            print(f"Error fetching data: {result.get('error')}")
            break

        data = result.get('data', {})
        records_data = data.get('data', [])
        fields = data.get('fields', [])
        field_ids = data.get('field_id_list', [])
        record_ids = data.get('record_id_list', [])

        for i, record_data in enumerate(records_data):
            record = {'record_id': record_ids[i] if i < len(record_ids) else None}
            for j, field_id in enumerate(field_ids):
                field_name = fields[j] if j < len(fields) else field_id
                value = record_data[j] if j < len(record_data) else None
                record[field_name] = value
            all_records.append(record)

        has_more = data.get('has_more', False)
        if not has_more:
            break
        offset += len(records_data)
        print(f"  已加载 {len(all_records)} 条记录...")

    return all_records


def convert_to_jpeg(src_path: Path, dst_path: Path) -> None:
    """将图片转换为 JPEG 格式（统一格式以保持顺序）"""
    img = Image.open(src_path)

    # 处理 RGBA 转为 RGB
    if img.mode == 'RGBA':
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # 保存为 JPEG（高质量95%）
    jpeg_path = dst_path.with_suffix('.jpeg')
    img.save(jpeg_path, 'JPEG', quality=95)
    return jpeg_path


def find_local_image(local_dir: Path, sample_id: str, model_key: str) -> Optional[Path]:
    """在本地目录查找匹配的图片"""
    for ext in ['*.png', '*.jpg', '*.jpeg']:
        for f in local_dir.glob(f"{sample_id}_*{ext}"):
            if model_key == 'nano':
                if '_nano' in f.name:
                    return f
            else:
                if '_nano' not in f.name:
                    return f
    return None


def download_attachment(file_token: str, output_path: Path) -> bool:
    """从飞书下载附件（使用 medias API）"""
    result = subprocess.run(
        ['lark-cli', 'api', 'GET',
         f'/open-apis/drive/v1/medias/{file_token}/download',
         '-o', str(output_path)],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def get_attachment_from_record(record: Dict, attachment_field: str = "生成图片") -> Optional[Dict]:
    """从记录中获取附件信息"""
    attachment = record.get(attachment_field)
    if not attachment:
        return None
    if isinstance(attachment, list) and len(attachment) > 0:
        att = attachment[0]
        if isinstance(att, dict) and att.get('file_token'):
            return {
                'file_token': att['file_token'],
                'name': att.get('name', 'unknown')
            }
    return None


def create_json_content(
    sample_id: str,
    prompt: str,
    checklist: str,
    category: str,
    difficulty: str,
    test_focus: str,
    has_text: str,
    real_model: str,
    file_index: int,
    is_model_b: bool = False
) -> Dict:
    """创建 JSON 内容

    Args:
        is_model_b: 是否为 B 图（奇数编号），B 图需要填写 GSB
    """
    model_code = MODEL_MAP.get(real_model, real_model)

    # B图使用带GSB的模板
    template = EVAL_TEMPLATE_B if is_model_b else EVAL_TEMPLATE_A

    # 根据是否含文字元素决定文字渲染评分项
    if has_text == "是":
        text_score_line = "文字渲染: ___分 (0/1/2)"
    else:
        text_score_line = "文字渲染: N/A (不含文字元素)"

    eval_text = template.format(
        sample_id=sample_id,
        category=category,
        difficulty=difficulty,
        test_focus=test_focus,
        has_text=has_text,
        prompt=prompt,
        checklist=checklist,
        text_score_line=text_score_line
    )

    return {
        "prompt": eval_text,
        "metadata": {
            "file_index": file_index,
            "sample_id": sample_id,
            "model_code": model_code,
            "is_model_b": is_model_b,
            "need_gsb": is_model_b,
            "_real_model": real_model,
            "original_prompt": prompt,
            "checklist": checklist,
            "category": category,
            "difficulty": difficulty,
            "test_focus": test_focus,
            "has_text_element": has_text,
            "created_at": datetime.now().isoformat()
        }
    }


def prepare_blind_test_data(
    base_token: str,
    table_id: str,
    local_images_dir: str,
    output_dir: str
):
    """准备盲测数据（文件从0开始，同样本A/B相邻）"""

    local_path = Path(local_images_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 从飞书加载数据
    print("正在从飞书多维表格加载元数据...")
    records = load_feishu_data(base_token, table_id)
    print(f"加载了 {len(records)} 条记录")

    # 按 sample_id 和模型分组
    samples = {}
    for record in records:
        sample_id = record.get('编号', '')
        feishu_model = record.get('模型', [''])[0] if isinstance(record.get('模型'), list) else record.get('模型', '')
        if not sample_id or not feishu_model:
            continue
        if sample_id not in samples:
            samples[sample_id] = {}

        real_model = FEISHU_MODEL_MAP.get(feishu_model, feishu_model)
        model_key = 'nano' if 'nano' in feishu_model.lower() else 'seedream'
        samples[sample_id][model_key] = {
            'record': record,
            'real_model': real_model
        }

    # 保存盲测密钥
    blind_key = {
        "model_map": MODEL_MAP,
        "sample_mapping": {},
        "file_mapping": {}
    }

    # 生成文件（从0开始，同样本A/B相邻）
    file_index = 0
    results = []
    missing_images = []

    for sample_id in sorted(samples.keys()):
        sample_data = samples[sample_id]

        # 固定顺序：先 A (seedream/doubao)，后 B (nano/gemini)
        for model_key in ['seedream', 'nano']:
            if model_key not in sample_data:
                continue

            item = sample_data[model_key]
            record = item['record']
            real_model = item['real_model']

            def get_field(r, name, default=''):
                v = r.get(name)
                if isinstance(v, list):
                    return v[0] if v else default
                return v if v else default

            prompt = get_field(record, '提示词')
            checklist = get_field(record, '检查点')
            category = get_field(record, '类目')
            difficulty = get_field(record, '难度')
            test_focus = get_field(record, '重点测试点')
            has_text = get_field(record, '是否含文字元素', '否')
            group = get_field(record, '分组', '')  # 获取分组字段

            # 查找本地图片
            local_image = find_local_image(local_path, sample_id, model_key)

            # 如果本地找不到，尝试从飞书下载
            if not local_image:
                attachment = get_attachment_from_record(record)
                if attachment:
                    # 下载到临时目录
                    temp_dir = output_path / "_temp_downloads"
                    temp_dir.mkdir(exist_ok=True)
                    temp_file = temp_dir / f"{sample_id}_{model_key}_{attachment['name']}"

                    print(f"  下载附件: {sample_id} ({model_key})...")
                    if download_attachment(attachment['file_token'], temp_file):
                        local_image = temp_file
                    else:
                        missing_images.append(f"{sample_id} ({model_key})")
                        print(f"  警告: 下载失败 {sample_id} ({model_key})")
                        continue
                else:
                    missing_images.append(f"{sample_id} ({model_key})")
                    print(f"  警告: 找不到图片 {sample_id} ({model_key})")
                    continue

            # 转换为 JPEG 格式（统一格式以保持顺序）
            image_filename = f"{file_index}.jpeg"
            jpeg_path = output_path / image_filename
            convert_to_jpeg(local_image, jpeg_path)

            # 创建 JSON（B图需要填写GSB）
            is_model_b = (model_key == 'nano')  # nano 是 Model B，奇数编号
            json_content = create_json_content(
                sample_id, prompt, checklist, category,
                difficulty, test_focus, has_text, real_model, file_index,
                is_model_b=is_model_b
            )
            # 添加分组信息到 metadata
            json_content["metadata"]["group"] = group
            with open(output_path / f"{file_index}.json", 'w', encoding='utf-8') as f:
                json.dump(json_content, f, ensure_ascii=False, indent=2)

            # 获取盲测编码
            model_code = MODEL_MAP.get(real_model, real_model)

            # 记录映射
            blind_key["file_mapping"][str(file_index)] = {
                "sample_id": sample_id,
                "model_code": model_code,
                "real_model": real_model,
                "group": group
            }

            if sample_id not in blind_key["sample_mapping"]:
                blind_key["sample_mapping"][sample_id] = {}
            blind_key["sample_mapping"][sample_id][model_code] = {
                "file_index": file_index,
                "real_model": real_model,
                "group": group
            }

            results.append({
                "file_index": file_index,
                "sample_id": sample_id,
                "model_code": model_code,
                "image": image_filename,
                "json": f"{file_index}.json",
                "group": group
            })
            print(f"  [{file_index}] {sample_id} - Model {model_code} ({group})")
            file_index += 1

    # 保存盲测密钥
    blind_key_path = output_path / "blind_key.json"
    with open(blind_key_path, 'w', encoding='utf-8') as f:
        json.dump(blind_key, f, ensure_ascii=False, indent=2)

    # 保存索引
    with open(output_path / "index.json", 'w', encoding='utf-8') as f:
        json.dump({
            "source": "feishu+local",
            "blind_test": True,
            "scoring": "0-1-2",
            "base_token": base_token,
            "table_id": table_id,
            "total_files": file_index,
            "samples": results,
            "missing_images": missing_images,
            "created_at": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)

    print(f"\n完成！共生成 {file_index} 对文件")
    print(f"⚠️  盲测密钥: {blind_key_path}")
    if missing_images:
        print(f"缺失图片: {len(missing_images)} 个")
    return results


def main():
    parser = argparse.ArgumentParser(
        description='准备百度千帆平台评测数据（A/B盲测 + 0,1,2三分制）'
    )
    parser.add_argument('--feishu', '-f', required=True,
                       help='飞书多维表格 (格式: base_token/table_id)')
    parser.add_argument('--images', '-i', required=True,
                       help='本地图片目录')
    parser.add_argument('--output', '-o', required=True,
                       help='输出目录')

    args = parser.parse_args()

    parts = args.feishu.split('/')
    if len(parts) != 2:
        parser.error("--feishu 格式应为: base_token/table_id")

    base_token, table_id = parts
    prepare_blind_test_data(
        base_token=base_token,
        table_id=table_id,
        local_images_dir=args.images,
        output_dir=args.output
    )


if __name__ == '__main__':
    main()
