# Akazik Skillhub

图像模型评测工作流 Skills 集合，用于 Claude Code 助手自动化评测流程。

## Skills

### eval-workflow

图像模型评测工作流：从飞书多维表格获取评测数据，按分组生成盲测打包文件（JSON+JPEG配对）。

**适用场景**：
- 准备评测数据 / 打包评测集 / 准备上传百度的数据
- 从飞书拉取评测数据 / 生成盲测包

**Shortcuts**：
- `+fetch` - 从飞书获取评测数据
- `+pack` - 本地打包
- `+reserve` - 预留导出到飞书文档（占位符）

### annotation-sync

标注结果收集与飞书同步工作流：从百度千帆平台导出的标注结果中提取评分，同步到飞书多维表格。

**适用场景**：
- 收集标注结果 / 同步评分到飞书
- 从百度标注数据提取分数
- 把评测结果写入飞书表格

**Shortcuts**：
- `+collect` - 收集标注结果
- `+sync` - 同步到飞书表格

## 安装

### 前置条件

1. Python 3.x
2. [lark-cli](https://github.com/nicepkg/lark-cli) - 飞书 CLI 工具

```bash
# 安装 lark-cli
npm install -g lark-cli

# 初始化配置
lark-cli config init --new

# 用户身份认证
lark-cli auth login --scope "base:app:read,base:record:read,drive:file:read"
```

### Python 依赖

```bash
pip install Pillow
```

## 配置

### 1. 复制 Skills 到项目

将 `skills/` 目录下的 skill 文件夹复制到你的项目 `.claude/skills/` 目录中。

### 2. 配置脱敏参数

编辑 `scripts/sync_to_feishu.py`，替换以下占位符：

```python
# 第 227 行
ID_FIELD_ID = 'YOUR_ID_FIELD_ID'  # 替换为你的飞书多维表格"编号"字段的 field_id
```

### 3. 获取 field_id

使用 lark-cli 获取字段信息：

```bash
lark-cli base +field-list --base-token YOUR_BASE_TOKEN --table-id YOUR_TABLE_ID
```

## 使用示例

### 准备评测数据

```bash
# 1. 从飞书获取数据
python3 scripts/prepare_eval_data.py \
  --feishu "YOUR_BASE_TOKEN/YOUR_TABLE_ID" \
  --images "./本地图片目录" \
  --output "./百度标注数据"

# 2. 打包
python3 scripts/pack_eval_data.py \
  --input "./百度标注数据" \
  --parts 2 \
  --output "./上传包"
```

### 收集并同步结果

```bash
# 1. 收集标注结果
python3 scripts/collect_results.py \
  --input "/path/to/标注结果目录" \
  --output "./results"

# 2. 同步到飞书
python3 scripts/sync_to_feishu.py \
  --data "./results/annotations.json" \
  --base "YOUR_BASE_TOKEN" \
  --table "YOUR_TABLE_ID" \
  --update
```

## 文档

- [多模态图像AI评测集构建指南](docs/多模态图像AI评测集构建指南.md)
- [开源评测集选择与构建指南](docs/开源评测集选择与构建指南.md)
- [图像模型竞品评测项目方案](docs/图像模型竞品评测项目方案.md)

## 评分体系

采用 0/1/2 三分制，维度权重如下：

| 维度 | 权重 |
|------|------|
| 提示词理解 | x3 |
| 合理性 | x3 |
| 图像质量 | x2 |
| 文字渲染 | x2 |
| 美观度 | x2 |

## 许可证

MIT
