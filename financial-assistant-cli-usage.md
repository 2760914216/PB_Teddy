# Financial Assistant CLI 使用说明

本文档说明本仓库中的财务问答命令行工具（Task2）的完整使用方式，包括环境准备、配置、预检、交互式问答、模型探测、批量验证、导出结果以及常见问题处理。

---

## 1. 工具简介

该工具的目标是：

- 接收中文自然语言财务问题
- 结合 MySQL 中已导入的财报结构化数据进行查询
- 在需要时生成趋势图表
- 输出中文答案
- 支持导出 `result/result_2.xlsx`

当前代码入口主要分为两类：

1. **正式交互入口**：`python3 -m src.task2.cli`
2. **辅助验证脚本**：`scripts/task2_preflight.py`、`scripts/task2_model_probe.py`、`scripts/task2_smoke_*.py`

---

## 2. 运行前提

在使用前，请确认以下条件成立：

### 2.1 Python 环境

项目约定使用 `~/.venv` + `uv` 的 Python 环境。

如果你已经在可用虚拟环境中，只需确认以下依赖可导入：

- `PyMySQL`
- `PyYAML`
- `pandas`
- `matplotlib`
- `openpyxl`

仓库中的 `requirements.txt` 已包含运行 Task2 所需依赖。

### 2.2 数据库前提

Task2 依赖 Task1 导入后的 MySQL 数据。

也就是说，数据库中至少应存在用于财务查询的表，例如：

- `income_sheet`
- `balance_sheet`
- `cash_flow_sheet`
- `core_performance_indicators_sheet`

### 2.3 Ollama 前提

默认模式下，CLI 会检查本地 Ollama 服务与模型是否可用。

当前默认配置中的模型是：

```yaml
ollama:
  host: "http://localhost:11434"
  model: "qwen3:14b"
```

如果你希望使用完整 LLM 路径，请先确保：

```bash
ollama serve
ollama list
ollama pull qwen3:14b
```

### 2.4 中文字体前提

图表绘制依赖系统字体。当前配置中的候选字体包括：

- `Noto Sans CJK JP`
- `Droid Sans Fallback`
- `Noto Sans CJK SC`
- `SimHei`
- `Microsoft YaHei`
- `WenQuanYi Zen Hei`

如果系统中没有这些字体，程序会给出 warning，并在需要图表时降级为“不生成图表”。

---

## 3. 配置文件说明

统一配置文件为仓库根目录下的：

```bash
config.yaml
```

当前关键配置如下：

```yaml
database:
  host: localhost
  port: 3306
  user: root
  password: ""
  database: financial_reports

ollama:
  host: "http://localhost:11434"
  model: "qwen3:14b"
  timeout_seconds: 60
  temperature: 0.0
  max_retries: 1

task2:
  result_dir: "result"
  chart_dir: "result"
  question_id_prefix: "B"
  max_rows: 50
  default_recent_years: 4
  max_turns: 10
  enable_charts: true
  sample_input_path: ""
```

### 字段解释

#### `database`

- `host` / `port`：MySQL 地址
- `user` / `password`：数据库用户名密码
- `database`：数据库名，当前默认是 `financial_reports`

#### `ollama`

- `host`：Ollama 服务地址
- `model`：默认模型名
- `timeout_seconds`：请求超时时间
- `temperature`：模型温度
- `max_retries`：JSON 解析失败时的重试次数

#### `task2`

- `result_dir`：结果输出目录
- `chart_dir`：图表输出目录
- `question_id_prefix`：默认题号前缀
- `max_rows`：单次 SQL 查询结果上限
- `default_recent_years`：类似“近几年”时默认解释为多少年
- `max_turns`：交互最大轮数
- `enable_charts`：是否启用图表
- `sample_input_path`：保留字段，可用于后续指定样例输入

---

## 4. 先做预检

建议每次正式使用前先执行预检：

```bash
python3 scripts/task2_preflight.py --config config.yaml
```

### 预检会检查什么

预检会检查以下项目：

- 数据库连接是否正常
- Ollama 服务是否可访问
- 配置中的模型是否存在
- `result/` 目录是否可写
- 是否存在可用中文字体

### 预检输出示例

成功时类似：

```text
database: ok
ollama: ok
model: ok (qwen3:14b)
result_dir: ok
chart_font: ok (...)
VERDICT: PASS
```

失败时类似：

```text
database: ok
ollama: fail (...)
model: fail (...)
result_dir: ok
chart_font: warn (...)
VERDICT: FAIL
```

如果默认模式预检失败，CLI 会拒绝启动。

---

## 5. 交互式 CLI 使用方式

正式交互入口：

```bash
python3 -m src.task2.cli --config config.yaml
```

### 可选参数

#### `--config`

指定配置文件路径：

```bash
python3 -m src.task2.cli --config config.yaml
```

#### `--question-id`

指定当前会话题号：

```bash
python3 -m src.task2.cli --config config.yaml --question-id B1002
```

如果生成图表，图片命名会基于题号进行，例如：

```text
./result/B1002_1.jpg
```

#### `--no-llm`

仅使用启发式规划，跳过模型调用：

```bash
python3 -m src.task2.cli --config config.yaml --no-llm
```

这个模式适合以下场景：

- 本地没有启动 Ollama
- 只想验证数据库查询和流程本身
- 想做本地 smoke test

注意：

- `--no-llm` 只会在**失败项仅限 `ollama` 和 `model`** 时绕过预检阻断
- 如果数据库、输出目录等关键检查失败，CLI 仍然不会启动

### CLI 内部命令

启动后可直接输入中文问题。

支持的控制命令：

- `help`：显示帮助
- `quit`：退出
- `exit`：退出

### CLI 交互示例

```text
task2> 金花股份2025年第三季度利润总额是多少
金花股份2025Q3的利润总额为 3533.59。
```

多轮追问示例：

```text
task2> 金花股份2025年第三季度利润总额是多少
金花股份2025Q3的利润总额为 3533.59。

task2> 那营业收入呢？
金花股份2025Q3的营业收入为 38390.84。
```

缺少条件时，CLI 会主动追问：

```text
task2> 金花股份利润总额是多少
请问你查询哪一个报告期的利润总额？例如 2025 年第三季度或 2024 年年报。
```

趋势问题示例：

```text
task2> 金花股份近几年的利润总额变化趋势是什么样的
金花股份2022FY到2025Q3的利润总额总体下降，由 4790.1 变为 3533.59，呈现明显波动并跨越盈亏分界。
图表: ./result/B1002_1.jpg
```

---

## 6. 模型探测（model probe）

如果你准备切换 Ollama 模型，建议先跑探测脚本：

```bash
python3 scripts/task2_model_probe.py --config config.yaml --model qwen3:14b
```

### 用途

该脚本会用预设问题样例测试候选模型是否能：

- 返回可解析 JSON
- 输出合法 SQL
- 输出中文分析文本

### 输出示例

```text
B1001 parseable=yes recommended=yes sql="SELECT ..."
B1002 parseable=yes recommended=yes sql="SELECT ..."
```

### 返回码说明

- 至少有一个 case 为 `recommended=yes` 时，脚本返回 0
- 否则返回 1

如果你准备替换默认模型，建议先用这个脚本确认候选模型质量。

---

## 7. 批量验证与导出

当前仓库提供的是**验证型批量脚本**，不是额外独立的正式批处理 CLI。

### 7.1 批量 smoke 测试

```bash
python3 scripts/task2_smoke_batch.py --config config.yaml --input 示例数据/task2_sample.json
```

### 参数说明

- `--config`：配置文件路径
- `--input`：附件4等价 JSON 输入
- `--use-llm`：可选，启用 Ollama 规划

### 输入格式说明

推荐使用类似仓库样例的结构：

```json
[
  {
    "编号": "B1001",
    "问题": [
      { "Q": "金花股份利润总额是多少" },
      { "Q": "2025年第三季度的" }
    ]
  }
]
```

### 输出内容

脚本会输出批量运行后的 JSON 结果，并打印：

```text
PASS: batch smoke succeeded
```

如果未传 `--input`，会直接失败：

```text
FAIL: missing Attachment4-equivalent sample input (--input)
```

---

### 7.2 导出 smoke 测试

```bash
python3 scripts/task2_smoke_export.py --config config.yaml --input 示例数据/task2_sample.json
```

该脚本会：

1. 运行批量问答
2. 生成 JSON 结果
3. 生成 Excel 结果
4. 读回 Excel 列名验证导出结构

### 导出结果位置

- JSON：`result/task2_answers.json`
- Excel：`result/result_2.xlsx`

### Excel 列结构

导出的 Excel 列名为：

```text
编号, 问题, SQL查询语句, 图形格式, 回答
```

### JSON 结果结构

当前 `result/task2_answers.json` 采用按题目分组的列表形式，每个元素包含：

- `编号`
- `回答`

其中 `回答` 是多轮 `{Q, A}` 结构数组。

示意：

```json
[
  {
    "编号": "B1002",
    "回答": [
      {
        "Q": "金花股份近几年的利润总额变化趋势是什么样的",
        "A": {
          "content": "...",
          "image": ["./result/B1002_1.jpg"]
        }
      }
    ]
  }
]
```

---

## 8. smoke 脚本总览

### CLI smoke

```bash
python3 scripts/task2_smoke_cli.py --config config.yaml
```

该脚本会以 `--no-llm` 模式启动 CLI，并自动输入：

- `help`
- `quit`

用于快速验证：

- 程序是否能启动
- 帮助文本是否正常
- 退出流程是否正常

### 批量 smoke

```bash
python3 scripts/task2_smoke_batch.py --config config.yaml --input 示例数据/task2_sample.json
```

### 导出 smoke

```bash
python3 scripts/task2_smoke_export.py --config config.yaml --input 示例数据/task2_sample.json
```

### 一键 demo

仓库还提供了脚本：

```bash
./scripts/task2_demo.sh
```

它会顺序执行：

1. `task2_preflight.py`
2. `task2_smoke_batch.py`
3. `task2_smoke_export.py`

如果你只是想快速验证当前 Task2 是否整体可运行，这是最省事的方式之一。

---

## 9. 输出文件说明

默认输出目录：

```bash
result/
```

常见输出文件包括：

- `result/result_2.xlsx`：Excel 主结果
- `result/task2_answers.json`：结构化 JSON 答案
- `result/B1002_1.jpg`：某题对应的图表
- `result/BCLI001_1.jpg`：交互式 CLI 默认题号产生的图表

### 图片命名规则

图表命名规则为：

```text
<题号>_<序号>.jpg
```

例如：

- `B1002_1.jpg`
- `BCLI001_1.jpg`

---

## 10. 常见使用场景

### 场景 A：正式运行前先检查环境

```bash
python3 scripts/task2_preflight.py --config config.yaml
```

如果 `VERDICT: PASS`，再启动默认 CLI。

---

### 场景 B：本地没有 Ollama，但想验证流程

```bash
python3 -m src.task2.cli --config config.yaml --no-llm
```

适用于：

- 本地数据库正常
- 想验证追问逻辑、SQL 安全、结果格式、导出流程
- 暂时不测试真实模型质量

---

### 场景 C：更换新模型前先做探测

```bash
python3 scripts/task2_model_probe.py --config config.yaml --model qwen3:14b
```

如果 probe 结果不好，不建议直接替换到生产配置。

---

### 场景 D：验证批量输入与导出结果

```bash
python3 scripts/task2_smoke_batch.py --config config.yaml --input 示例数据/task2_sample.json
python3 scripts/task2_smoke_export.py --config config.yaml --input 示例数据/task2_sample.json
```

运行后检查：

- `result/task2_answers.json`
- `result/result_2.xlsx`
- `result/*.jpg`

---

## 11. 常见问题排查

### 11.1 `ollama: fail`

说明本地 Ollama 服务没有启动，或者 `host` 配置不对。

先检查：

```bash
ollama serve
curl http://localhost:11434/api/tags
```

### 11.2 `model: fail`

说明配置中的模型在本地不存在。

例如当前配置是：

```yaml
model: "qwen3:14b"
```

则需要：

```bash
ollama pull qwen3:14b
```

### 11.3 `database: fail`

说明 MySQL 无法连接，常见原因包括：

- 端口不对
- 用户名密码不对
- 数据库名不对
- MySQL 服务没启动

先检查 `config.yaml` 的 `database` 段。

### 11.4 图表没有生成

可能原因：

1. 问题本身不适合生成图表（例如单值问题）
2. 系统没有可用中文字体
3. 当前结果不足以绘图
4. `task2.enable_charts` 被关闭

建议先跑：

```bash
python3 scripts/task2_preflight.py --config config.yaml
```

重点看：

```text
chart_font: ok / warn
```

### 11.5 CLI 启动即退出

先看预检输出是否有失败项。

如果只是 Ollama / model 失败，但你只是想测试流程，可改用：

```bash
python3 -m src.task2.cli --config config.yaml --no-llm
```

### 11.6 批量脚本提示缺少输入

必须显式传入：

```bash
--input 示例数据/task2_sample.json
```

---

## 12. 推荐使用顺序

如果你第一次使用，推荐按下面顺序执行：

### 路线 1：完整模式（有 Ollama）

```bash
python3 scripts/task2_preflight.py --config config.yaml
python3 scripts/task2_model_probe.py --config config.yaml --model qwen3:14b
python3 -m src.task2.cli --config config.yaml
```

### 路线 2：本地流程验证（无 Ollama）

```bash
python3 -m src.task2.cli --config config.yaml --no-llm
python3 scripts/task2_smoke_batch.py --config config.yaml --input 示例数据/task2_sample.json
python3 scripts/task2_smoke_export.py --config config.yaml --input 示例数据/task2_sample.json
```

### 路线 3：快速一键验证

```bash
./scripts/task2_demo.sh
```

---

## 13. 当前仓库中最常用的几个命令

```bash
# 1) 预检
python3 scripts/task2_preflight.py --config config.yaml

# 2) 默认交互式 CLI
python3 -m src.task2.cli --config config.yaml

# 3) 无模型本地验证模式
python3 -m src.task2.cli --config config.yaml --no-llm

# 4) 探测模型是否适合 Task2
python3 scripts/task2_model_probe.py --config config.yaml --model qwen3:14b

# 5) 批量 smoke
python3 scripts/task2_smoke_batch.py --config config.yaml --input 示例数据/task2_sample.json

# 6) 导出 smoke
python3 scripts/task2_smoke_export.py --config config.yaml --input 示例数据/task2_sample.json

# 7) 一键 demo
./scripts/task2_demo.sh
```

---

如果后续你希望我继续补一版“面向最终用户的精简版说明”或者“面向开发者的部署说明”，可以在此文件基础上再拆分。 
