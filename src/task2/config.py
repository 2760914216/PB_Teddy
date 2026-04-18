from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import yaml


class Task2ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "financial_reports"


@dataclass(frozen=True)
class OllamaConfig:
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    timeout_seconds: int = 60
    temperature: float = 0.0
    max_retries: int = 1


@dataclass(frozen=True)
class Task2RuntimeConfig:
    result_dir: str = "result"
    chart_dir: str = "result"
    question_id_prefix: str = "B"
    max_rows: int = 50
    default_recent_years: int = 4
    max_turns: int = 10
    max_clarification_turns: int = 3
    enable_charts: bool = True
    judge_enabled: bool = True
    judge_confidence_threshold: float = 0.8
    judge_timeout_seconds: int = 30
    judge_max_retries: int = 0
    sample_input_path: str = ""
    chart_font_candidates: tuple[str, ...] = (
        "Noto Sans CJK JP",
        "Droid Sans Fallback",
        "Noto Sans CJK SC",
        "SimHei",
        "Microsoft YaHei",
        "WenQuanYi Zen Hei",
    )


@dataclass(frozen=True)
class Task2Config:
    config_path: Path
    root_dir: Path
    database: DatabaseConfig
    ollama: OllamaConfig
    task2: Task2RuntimeConfig
    raw: dict[str, object] = field(default_factory=dict)

    def resolve_path(self, relative_or_absolute: str) -> Path:
        path = Path(relative_or_absolute)
        if path.is_absolute():
            return path
        return (self.root_dir / path).resolve()

    @property
    def result_dir_path(self) -> Path:
        return self.resolve_path(self.task2.result_dir)

    @property
    def chart_dir_path(self) -> Path:
        return self.resolve_path(self.task2.chart_dir or self.task2.result_dir)

    @property
    def sample_input_path(self) -> Path | None:
        if not self.task2.sample_input_path:
            return None
        return self.resolve_path(self.task2.sample_input_path)

    def ensure_output_dirs(self) -> None:
        self.result_dir_path.mkdir(parents=True, exist_ok=True)
        self.chart_dir_path.mkdir(parents=True, exist_ok=True)


def _load_yaml(config_path: Path) -> dict[str, object]:
    if not config_path.exists():
        raise Task2ConfigError(f"配置文件不存在: {config_path}")
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise Task2ConfigError(f"配置文件解析失败: {config_path}") from exc


def _as_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        mapped: dict[str, object] = {}
        raw_mapping = cast(dict[object, object], value)
        for key, item in raw_mapping.items():
            mapped[str(key)] = item
        return mapped
    return {}


def _coerce_str(value: object, *, default: str) -> str:
    if value is None:
        return default
    return str(value)


def _coerce_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise Task2ConfigError(f"无法解析整数配置值: {value!r}")


def _coerce_float(value: object, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    raise Task2ConfigError(f"无法解析浮点配置值: {value!r}")


def _coerce_str_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise Task2ConfigError("task2.chart_font_candidates 必须是列表")
    raw_list = cast(list[object], value)
    return tuple(str(item) for item in raw_list)


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def load_task2_config(config_path: str = "config.yaml") -> Task2Config:
    absolute_path = Path(config_path).expanduser().resolve()
    payload = _load_yaml(absolute_path)

    database_raw = _as_mapping(payload.get("database"))
    ollama_raw = _as_mapping(payload.get("ollama"))
    task2_raw = _as_mapping(payload.get("task2"))

    database = DatabaseConfig(
        host=_coerce_str(database_raw.get("host"), default="localhost"),
        port=_coerce_int(database_raw.get("port"), default=3306),
        user=_coerce_str(database_raw.get("user"), default="root"),
        password=_coerce_str(database_raw.get("password"), default=""),
        database=_coerce_str(database_raw.get("database"), default="financial_reports"),
    )

    ollama = OllamaConfig(
        host=_coerce_str(
            ollama_raw.get("host"), default="http://localhost:11434"
        ).rstrip("/"),
        model=_coerce_str(ollama_raw.get("model"), default="qwen2.5:7b"),
        timeout_seconds=_coerce_int(ollama_raw.get("timeout_seconds"), default=60),
        temperature=_coerce_float(ollama_raw.get("temperature"), default=0.0),
        max_retries=_coerce_int(ollama_raw.get("max_retries"), default=1),
    )

    font_candidates = _coerce_str_list(task2_raw.get("chart_font_candidates"))

    task2 = Task2RuntimeConfig(
        result_dir=_coerce_str(task2_raw.get("result_dir"), default="result"),
        chart_dir=_coerce_str(
            task2_raw.get("chart_dir", task2_raw.get("result_dir")),
            default="result",
        ),
        question_id_prefix=_coerce_str(
            task2_raw.get("question_id_prefix"), default="B"
        ),
        max_rows=max(1, _coerce_int(task2_raw.get("max_rows"), default=50)),
        default_recent_years=max(
            2, _coerce_int(task2_raw.get("default_recent_years"), default=4)
        ),
        max_turns=max(1, _coerce_int(task2_raw.get("max_turns"), default=10)),
        max_clarification_turns=max(
            1, _coerce_int(task2_raw.get("max_clarification_turns"), default=3)
        ),
        enable_charts=_coerce_bool(task2_raw.get("enable_charts"), default=True),
        judge_enabled=_coerce_bool(task2_raw.get("judge_enabled"), default=True),
        judge_confidence_threshold=max(
            0.0,
            min(
                1.0,
                _coerce_float(task2_raw.get("judge_confidence_threshold"), default=0.8),
            ),
        ),
        judge_timeout_seconds=max(
            1,
            _coerce_int(
                task2_raw.get("judge_timeout_seconds", ollama.timeout_seconds),
                default=ollama.timeout_seconds,
            ),
        ),
        judge_max_retries=max(
            0,
            _coerce_int(
                task2_raw.get("judge_max_retries", ollama.max_retries),
                default=ollama.max_retries,
            ),
        ),
        sample_input_path=_coerce_str(task2_raw.get("sample_input_path"), default=""),
        chart_font_candidates=font_candidates
        or Task2RuntimeConfig.chart_font_candidates,
    )

    config = Task2Config(
        config_path=absolute_path,
        root_dir=absolute_path.parent,
        database=database,
        ollama=ollama,
        task2=task2,
        raw=payload,
    )
    return config
