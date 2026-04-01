#!/usr/bin/env python3
"""
评测数据打包脚本
================
将生成的评测数据分片打包为 zip 文件，便于上传到标注平台。

用法:
  python3 pack_eval_data.py --input ./百度标注数据 --parts 2 --output ./上传包
"""

import os
import json
import zipfile
import argparse
import shutil
from pathlib import Path
from datetime import datetime


def pack_data(input_dir: str, parts: int, output_dir: str):
    """分片打包评测数据

    Args:
        input_dir: 包含评测数据的目录（有 index.json）
        parts: 分片数量
        output_dir: 输出目录
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 读取索引
    index_path = input_path / "index.json"
    if not index_path.exists():
        print(f"错误: 找不到索引文件 {index_path}")
        return False

    with open(index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)

    total_files = index['total_files']

    # 验证分片数
    if parts <= 0:
        print("错误: 分片数必须大于 0")
        return False

    if parts > total_files:
        print(f"警告: 分片数 ({parts}) 大于文件对数 ({total_files})，调整为 {total_files}")
        parts = total_files

    # 计算每个包的文件数
    files_per_part = total_files // parts
    remainder = total_files % parts

    manifest = {
        "total_files": total_files,
        "parts": parts,
        "packages": [],
        "source_dir": str(input_path.absolute()),
        "created_at": datetime.now().isoformat()
    }

    current = 0
    for i in range(parts):
        # 分配文件数（前面的包多分余数）
        count = files_per_part + (1 if i < remainder else 0)
        start = current
        end = current + count
        current = end

        # 创建 zip 文件
        zip_path = output_path / f"part_{i+1}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for j in range(start, end):
                jpeg_file = input_path / f"{j}.jpeg"
                json_file = input_path / f"{j}.json"

                if jpeg_file.exists():
                    zf.write(jpeg_file, f"{j}.jpeg")
                else:
                    print(f"警告: 找不到图片 {jpeg_file}")

                if json_file.exists():
                    zf.write(json_file, f"{j}.json")
                else:
                    print(f"警告: 找不到 JSON {json_file}")

        package_info = {
            "filename": f"part_{i+1}.zip",
            "file_range": [start, end - 1],
            "file_count": count,
            "size_mb": round(zip_path.stat().st_size / (1024 * 1024), 2)
        }
        manifest["packages"].append(package_info)
        print(f"Created {zip_path.name} ({count} pairs, indices {start}-{end-1})")

    # 复制 blind_key.json 到输出目录（重要！）
    blind_key_src = input_path / "blind_key.json"
    if blind_key_src.exists():
        shutil.copy(blind_key_src, output_path / "blind_key.json")
        print("Copied blind_key.json to output directory")
    else:
        print("警告: 找不到 blind_key.json")

    # 保存 manifest
    with open(output_path / "manifest.json", 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"打包完成!")
    print(f"{'='*50}")
    print(f"输出目录: {output_path.absolute()}")
    print(f"总文件对: {total_files}")
    print(f"分片数: {parts}")
    print(f"\n包列表:")
    for pkg in manifest["packages"]:
        print(f"  - {pkg['filename']}: {pkg['file_count']} 对 ({pkg['size_mb']} MB)")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='打包评测数据为分片 zip 文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 pack_eval_data.py -i ./百度标注数据 -p 2 -o ./上传包
        """
    )
    parser.add_argument('--input', '-i', required=True,
                       help='输入目录（包含生成的数据）')
    parser.add_argument('--parts', '-p', type=int, required=True,
                       help='分片数量')
    parser.add_argument('--output', '-o', required=True,
                       help='输出目录')

    args = parser.parse_args()
    pack_data(args.input, args.parts, args.output)


if __name__ == '__main__':
    main()
