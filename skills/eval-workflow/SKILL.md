---
name: eval-workflow
version: 2.0.0
description: "图像模型评测工作流：从飞书多维表格获取评测数据，按分组生成盲测打包文件（JSON+JPEG配对）。当用户需要准备评测数据、按分组打包上传百度千帆平台时使用。"
metadata:
  requires:
    bins: ["lark-cli", "python3"]
    scripts:
      - "scripts/prepare_eval_data.py"
      - "scripts/pack_eval_data.py"
      - "scripts/collect_results.py"
      - "scripts/sync_to_feishu.py"
---

# 图像模型评测工作流 (v1)

## 适用场景

- "准备评测数据" / "打包评测集" / "准备上传百度的数据"
- "从飞书拉取评测数据" / "生成盲测包"
- "我要做图像模型评测"

## 工作流概览

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Step 1     │    │  Step 2     │    │  Step 3     │
│  +fetch     │───►│  +pack      │───►│  +reserve   │
│  从飞书获取  │    │  本地打包    │    │  预留导出    │
└─────────────┘    └─────────────┘    └─────────────┘
```

## 配置参数

配置文件位于 `config.json`，可修改模型映射、评分权重等。

### 模型映射（盲测编码）

| 盲测编码 | 真实模型名 |
|----------|-----------|
| Model A | model-a |
| Model B | model-b |

> 注：实际使用时请在 `config.json` 中配置真实的模型名称。

### 评分制

- 0/1/2 三分制

## Shortcuts

### +fetch - 从飞书获取评测数据

从飞书多维表格拉取 prompts 和元数据，匹配本地图片，生成 JSON+JPEG 文件对。

**使用方式：**

执行 `+fetch` 时，需向用户询问以下信息：
1. 飞书多维表格地址（或 base_token/table_id）
2. 本地图片目录路径
3. 输出目录路径

**执行命令：**
```bash
python3 scripts/prepare_eval_data.py \
  --feishu "<base_token>/<table_id>" \
  --images "<local_images_dir>" \
  --output "<output_dir>"
```

**输出文件：**
```
{output_dir}/
├── 0.jpeg, 0.json        # 样本 1 - Model A
├── 1.jpeg, 1.json        # 样本 1 - Model B (含 GSB)
├── 2.jpeg, 2.json        # 样本 2 - Model A
├── 3.jpeg, 3.json        # 样本 2 - Model B (含 GSB)
├── ...
├── blind_key.json        # 盲测密钥（重要！）
└── index.json            # 索引文件
```

**注意事项：**
- 偶数编号 (0, 2, 4...) → Model A
- 奇数编号 (1, 3, 5...) → Model B
- 同一样本的两张图编号相邻
- 不含文字元素的样本，文字渲染评分自动设为 N/A

---

### +pack - 本地打包

对已生成的数据进行分片打包，便于上传到标注平台。

**使用方式：**

执行 `+pack` 时，**必须先询问用户**：
> "当前有 X 对文件，请输入要分成几个包？"

等待用户回复后，使用用户输入的数字作为分片数。

**执行命令：**
```bash
python3 scripts/pack_eval_data.py \
  --input "<data_dir>" \
  --parts <N> \
  --output "<package_dir>"
```

**输出文件：**
```
{package_dir}/
├── part_1.zip            # 第 1 个上传包
├── part_2.zip            # 第 2 个上传包
├── ...
├── blind_key.json        # 盲测密钥（需妥善保管）
└── manifest.json         # 打包清单
```

---

### +reserve - 预留导出到飞书文档

> **状态：** 占位符，未实现

为未来功能预留的接口，用于将评测结果导出到飞书文档。

**当前行为：**
```
该功能尚未实现，敬请期待。

如需同步结果到飞书多维表格，可使用以下脚本：
python3 scripts/sync_to_feishu.py --data ./results/feishu_import.csv
```

## 前置条件

### 1. 系统依赖

| 依赖 | 安装方式 | 用途 |
|------|----------|------|
| Python 3.x | 系统自带或 `brew install python3` | 运行脚本 |
| lark-cli | `npm install -g lark-cli` | 飞书 API 调用 |
| Pillow | `pip install Pillow` | 图片格式转换 |

### 2. lark-cli 认证

```bash
# 初始化配置
lark-cli config init --new

# 用户身份认证（读取多维表格）
lark-cli auth login --scope "base:app:read,base:record:read"

# 验证认证状态
lark-cli auth status
```

### 3. 飞书权限要求

| 操作 | 所需 Scope | 说明 |
|------|-----------|------|
| 读取多维表格 | `base:app:read` | 读取 Base 应用信息 |
| 读取记录 | `base:record:read` | 读取表格记录数据 |
| 写入记录（预留） | `base:record:create` | 后续同步结果时需要 |

### 4. 飞书多维表格字段要求

源表格需包含以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 编号 | 文本 | 样本唯一标识（如 A-001） |
| 提示词 | 文本 | 生图 prompt |
| 检查点 | 文本 | 检查要素列表 |
| 类目 | 单选 | 图片类目（动物、人物等） |
| 难度 | 单选 | 基准/进阶/高难度 |
| 重点测试点 | 文本 | 测试重点 |
| 是否含文字元素 | 单选 | 是/否 |
| 模型 | 单选 | ModelA / ModelB |

### 5. 本地图片命名规范

图片文件需按以下规则命名：
```
{样本编号}_{模型标识}.{扩展名}

示例:
A-001_model_a.png  → Model A 生成的图
A-001_model_b.png  → Model B 生成的图
```

## 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| lark-cli 未认证 | 提示执行 `lark-cli auth login --scope "base:app:read,base:record:read"` |
| 找不到多维表格 | 检查 base_token 和 table_id 是否正确 |
| 权限不足 | 提示用户联系管理员开通权限 |
| 找不到本地图片 | 警告并跳过，列出缺失文件清单 |
| 图片格式不支持 | 自动转换为 JPEG（RGBA → RGB） |
| 分片数量无效 | 提示重新输入有效数字 |
| 输出目录已存在 | 覆盖已有文件 |

## 完整工作流示例

```
用户: 准备评测数据

Agent: 请提供以下信息：
       1. 飞书多维表格地址
       2. 本地图片目录
       3. 输出目录

用户: 表格: PlWcbSE0hauAoSsUxUlcnmVmnhd/tblBPGv7aaI5nx32
      图片: ./试标
      输出: ./百度标注数据

Agent: [执行 +fetch]
       加载了 24 条记录
       匹配成功: 24 对
       完成！输出目录: ./百度标注数据

用户: 打包

Agent: 当前有 24 对文件，请输入要分成几个包？

用户: 2

Agent: [执行 +pack]
       Created part_1.zip (12 pairs)
       Created part_2.zip (12 pairs)
       完成！

用户: 导出到飞书文档

Agent: [执行 +reserve]
       该功能尚未实现，敬请期待。
```

## 相关资源

- [config.json](config.json) - 配置文件（评分模板、模型映射、权重）
- [scripts/](scripts/) - 脚本目录
  - `prepare_eval_data.py` - 数据准备脚本
  - `pack_eval_data.py` - 打包脚本
  - `collect_results.py` - 结果收集脚本
  - `sync_to_feishu.py` - 飞书同步脚本
