# Task2 运行手册

## 环境前提

- Python 运行环境按 `~/.venv` + `uv` 约定执行
- 配置统一来自仓库根目录 `config.yaml`
- 依赖 MySQL 已导入任务1数据
- 依赖本地 Ollama；若模型未拉取，预检会明确失败并提示先拉模型
- 若系统缺少中文字体，图表会降级为不生成

## 关键命令

### preflight

```bash
python3 scripts/task2_preflight.py --config config.yaml
```

### model_probe

```bash
python3 scripts/task2_model_probe.py --config config.yaml --model qwen2.5:7b
```

### cli

```bash
python3 -m src.task2.cli --config config.yaml
python3 -m src.task2.cli --config config.yaml --no-llm
```

### batch

```bash
python3 scripts/task2_smoke_batch.py --config config.yaml --input 示例数据/task2_sample.json
```

### export / result_2.xlsx

```bash
python3 scripts/task2_smoke_export.py --config config.yaml --input 示例数据/task2_sample.json
```

输出目录默认是 `result/`，Excel 文件为 `result/result_2.xlsx`。

## 已决议默认项

- batch 输入基准：优先使用题面表1等价 JSON；仓库内提供 `示例数据/task2_sample.json` 作为最小样例
- 图片命名：统一使用完整题号，例如 `B1002_1.jpg`
- 图表按需生成；单值查询默认不生成图片

## 已知风险 / 待确认项

- 默认 CLI 若 Ollama 未启动或模型未拉取会被预检阻断；若只想做本地启发式验证，可使用 `--no-llm`
- 当前环境若没有中文字体，趋势题会返回无图答案并给出预检 warning
- 若后续拿到正式附件4，可直接替换 `--input` 为正式等价 JSON
