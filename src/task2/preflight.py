from __future__ import annotations

import json
import urllib.error
import urllib.request

import matplotlib
from matplotlib import font_manager
import pymysql

from .config import Task2Config, load_task2_config


def _check_database(config: Task2Config) -> dict[str, object]:
    try:
        connection = pymysql.connect(
            host=config.database.host,
            port=config.database.port,
            user=config.database.user,
            password=config.database.password,
            database=config.database.database,
            cursorclass=pymysql.cursors.DictCursor,
            charset="utf8mb4",
            autocommit=True,
        )
        connection.close()
        return {"status": "ok", "fatal": True, "message": "database: ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "fail", "fatal": True, "message": f"database: fail ({exc})"}


def _check_ollama(config: Task2Config) -> tuple[dict[str, object], dict[str, object]]:
    request = urllib.request.Request(f"{config.ollama.host}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(
            request, timeout=config.ollama.timeout_seconds
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        failure: dict[str, object] = {
            "status": "fail",
            "fatal": True,
            "message": f"ollama: fail ({exc})",
        }
        model_failure: dict[str, object] = {
            "status": "fail",
            "fatal": True,
            "message": f"model: fail ({config.ollama.model})",
        }
        return failure, model_failure

    models = payload.get("models") if isinstance(payload, dict) else []
    names = {str(item.get("name")) for item in models or [] if isinstance(item, dict)}
    ollama_result: dict[str, object] = {
        "status": "ok",
        "fatal": True,
        "message": "ollama: ok",
    }
    if config.ollama.model in names:
        model_result: dict[str, object] = {
            "status": "ok",
            "fatal": True,
            "message": f"model: ok ({config.ollama.model})",
        }
    else:
        model_result = {
            "status": "fail",
            "fatal": True,
            "message": f"model: fail ({config.ollama.model}, pull model first)",
        }
    return ollama_result, model_result


def _check_output_dir(config: Task2Config) -> dict[str, object]:
    try:
        config.ensure_output_dirs()
        probe = config.result_dir_path / ".task2_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"status": "ok", "fatal": True, "message": "result_dir: ok"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "fail", "fatal": True, "message": f"result_dir: fail ({exc})"}


def _check_chart_font(config: Task2Config) -> dict[str, object]:
    available = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in config.task2.chart_font_candidates:
        if candidate in available:
            return {
                "status": "ok",
                "fatal": False,
                "message": f"chart_font: ok ({candidate})",
            }
    return {
        "status": "warn",
        "fatal": False,
        "message": "chart_font: warn (未找到可用中文字体，图表将降级为不生成)",
    }


def run_preflight(config: str | Task2Config = "config.yaml") -> dict[str, object]:
    loaded_config = load_task2_config(config) if isinstance(config, str) else config
    matplotlib.use("Agg")
    database_result = _check_database(loaded_config)
    ollama_result, model_result = _check_ollama(loaded_config)
    output_result = _check_output_dir(loaded_config)
    font_result = _check_chart_font(loaded_config)
    checks = {
        "database": database_result,
        "ollama": ollama_result,
        "model": model_result,
        "result_dir": output_result,
        "chart_font": font_result,
    }
    fatal_failed = any(
        str(item.get("status")) == "fail" and bool(item.get("fatal"))
        for item in checks.values()
    )
    return {"checks": checks, "ok": not fatal_failed}
