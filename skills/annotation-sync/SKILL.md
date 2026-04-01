---
name: annotation-sync
version: 1.0.0
description: "标注结果收集与飞书同步工作流：从百度千帆平台导出的标注结果中提取评分，同步到飞书多维表格。"
metadata:
  requires:
    bins: ["python3", "lark-cli"]
    files:
      - scripts/collect_results.py
      - scripts/sync_to_feishu.py
---

# 标注结果收集与同步工作流

## 适用场景

- "收集标注结果" / "同步评分到飞书"
- "从百度标注数据提取分数"
- "把评测结果写入飞书表格"

## 工作流概览

```
┌─────────────┐    ┌─────────────┐
│  Step 1     │    │  Step 2     │
│  +collect   │───►│  +sync      │
│  收集结果    │    │  同步飞书    │
└─────────────┘    └─────────────┘
```

## 评分体系

### 维度权重（0/1/2 三分制）

| 维度 | 权重 |
|------|------|
| 提示词理解 | ×3 |
| 合理性 | ×3 |
| 图像质量 | ×2 |
| 文字渲染 | ×2 |
| 美观度 | ×2 |

### 错误类型编码

| 序号 | 错误类型 |
|------|----------|
| 1 | 跑题/主体错误 |
| 2 | 关键属性错误 |
| 3 | 数量错误 |
| 4 | 位置关系错误 |
| 5 | 否定指令未执行 |
| 6 | 文字错误 |
| 7 | 人体/结构异常 |
| 8 | 光影/反射不合理 |
| 9 | 多余元素干扰 |
| 10 | 清晰度/细节不足 |
| 11 | 无明显错误（默认值） |

### GSB 判断

- **G**: A 图整体优于 B 图
- **S**: 两图整体相当
- **B**: B 图整体优于 A 图

#### GSB 合并规则

GSB 可能写在 A 图或 B 图任意一张上，收集时按以下规则处理：

| 情况 | 处理方式 |
|------|----------|
| A图有GSB，B图没有 | 使用A图的GSB |
| B图有GSB，A图没有 | 使用B图的GSB，写入A图那一栏 |
| A图和B图都有，且相同 | 合并使用A图的 |
| A图和B图都有，但不同 | 标记为冲突 `A:G / B:S`，交由质检处理 |

冲突记录在导出时会标记 ⚠️ 符号。

## Shortcuts

### +collect - 收集标注结果

从百度千帆导出的标注目录中提取评分数据。

**使用方式：**

```bash
python3 scripts/collect_results.py \
  --input "<标注结果目录>" \
  --output "<输出目录>"
```

**支持的评分格式：**

评分解析自动处理以下格式：
- `提示词理解: 2分`
- `提示词理解: __2__`
- `提示词理解: _1_分 (0/1/2)`
- `提示词理解: N/A` → 返回 null

**GSB 解析支持：**
1. 标准 GSB 判断字段: `GSB判断: G`
2. 备注后（可能隔空行）: `备注: xxx\n\nG`
3. 文末单独一行: 最后 5 行内的 G/S/B

**GSB 保存位置：**
- GSB 保留在各自图对应的记录上（A 图的 GSB 在 A 记录，B 图的 GSB 在 B 记录）
- 如果 A/B 图都写了 GSB 且不同，标记为冲突 `A:G / B:S`

**输出文件：**
```
{output_dir}/
├── annotations.json    # 完整标注数据
├── summary.json        # 汇总统计
└── feishu_import.csv   # 飞书导入格式
```

---

### +sync - 同步到飞书表格

将收集的结果同步到飞书多维表格。

**使用方式：**

```bash
python3 scripts/sync_to_feishu.py \
  --data "<annotations.json 或 feishu_import.csv>" \
  --base "<base_token>" \
  --table "<table_id>" \
  --update
```

**参数说明：**
- `--update`: 更新模式，按"编号"字段匹配已有记录
- `--create`: 新增模式，创建新记录

**字段映射：**

| CSV 字段 | 飞书字段名 |
|----------|-----------|
| score_prompt | 提示词理解(×3) |
| score_rationality | 合理性(×3) |
| score_quality | 图像质量(×2) |
| score_text | 文字渲染(×2) |
| score_aesthetic | 美观度(×2) |
| weighted_total | 加权总分 |
| error_types | 错误类型 |
| gsb | GSB |
| remarks | 题目备注 |

## 完整工作流示例

```bash
# Step 1: 收集标注结果
python3 scripts/collect_results.py \
  --input "/Users/twzl/Downloads/正式标注集v2" \
  --output "./results"

# Step 2: 同步到飞书表格
python3 scripts/sync_to_feishu.py \
  --data "./results/annotations.json" \
  --base "WAYYbKiipaY6U3s341QcxHwdnKe" \
  --table "tblQJdK3wEGYFuY3" \
  --update
```

## 注意事项

### 飞书 API 字段顺序问题

⚠️ **重要**: 飞书多维表格 API 返回的字段顺序在不同请求/分页中可能不同，必须使用 `field_id_list` 定位字段索引，且**每页都需要重新计算索引**。

```python
# 错误做法 - 硬编码索引或只计算一次
id_idx = fields.index('编号')  # 第一页的索引
# 第二页可能字段顺序不同！

# 正确做法 - 每页用 field_id 动态查找
ID_FIELD_ID = "fld64hLsFo"  # 编号字段的 field_id（固定）
for page in pages:
    field_ids = page['data']['field_id_list']
    id_idx = field_ids.index(ID_FIELD_ID)  # 每页重新计算
    # 使用 id_idx...
```

### 分页处理

加载大量记录时必须处理分页，循环请求直到 `has_more` 为 false：

```python
offset = 0
while True:
    result = lark_cli base +record-list --offset {offset} --limit 500
    records = result['data']['data']
    # 处理记录...
    offset += len(records)
    if not result['data']['has_more']:
        break
```

### 附件下载

多维表格附件不能用 `lark-cli drive +download`，需使用 medias API：

```bash
lark-cli api GET "/open-apis/drive/v1/medias/{file_token}/download" -o "output.jpg"
```

## 相关资源

- [collect_results.py](scripts/collect_results.py) - 标注结果收集脚本
- [sync_to_feishu.py](scripts/sync_to_feishu.py) - 飞书同步脚本
- [feishu-bitable-field-order.md](~/.claude/projects/-Users-twzl/memory/feishu-bitable-field-order.md) - 字段顺序问题备忘
