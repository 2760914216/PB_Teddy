from __future__ import annotations

import argparse
import importlib
import logging
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _print_help() -> None:
    print("输入中文财务问题开始查询；输入 help 查看说明，输入 quit/exit 退出。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Task2 智能问数 CLI")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--question-id", default="BCLI001", help="当前会话的问题编号")
    parser.add_argument(
        "--no-llm", action="store_true", help="仅使用启发式规划，跳过模型调用"
    )
    args = parser.parse_args()

    preflight_module = importlib.import_module("src.task2.preflight")
    recovery_module = importlib.import_module("src.task2.recovery")
    runtime_module = importlib.import_module("src.task2.runtime")
    session_module = importlib.import_module("src.task2.session")

    run_preflight = getattr(preflight_module, "run_preflight")
    format_recovery_message = getattr(recovery_module, "format_recovery_message")
    handle_turn = getattr(runtime_module, "handle_turn")
    session_class = getattr(session_module, "Task2Session")

    report = run_preflight(args.config)
    checks = report.get("checks") if isinstance(report, dict) else {}
    if isinstance(checks, dict):
        for item in checks.values():
            if isinstance(item, dict):
                print(item.get("message"))
    preflight_ok = bool(report.get("ok"))
    if args.no_llm and not preflight_ok:
        failed_checks = [
            key
            for key, item in checks.items()
            if isinstance(item, dict) and item.get("status") == "fail"
        ]
        if set(failed_checks).issubset({"ollama", "model"}):
            preflight_ok = True
            logger.warning("以 --no-llm 模式跳过 Ollama/模型预检失败。")
    if not preflight_ok:
        logger.error("预检失败，CLI 未启动。")
        return 1

    session = session_class()
    print("Task2 智能问数 CLI 已启动。")
    _print_help()

    while True:
        try:
            question = input("task2> ").strip()
        except EOFError:
            print()
            return 0

        if not question:
            continue
        if question.lower() in {"quit", "exit"}:
            return 0
        if question.lower() == "help":
            _print_help()
            continue

        try:
            result = handle_turn(
                session,
                question,
                config=args.config,
                question_id=args.question_id,
                use_llm=not args.no_llm,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Task2 turn failed")
            print(format_recovery_message(exc))
            continue
        answer = result.get("answer") if isinstance(result, dict) else {}
        if isinstance(answer, dict):
            print(answer.get("content", ""))
            images = answer.get("image")
            if isinstance(images, list) and images:
                print("图表:", ", ".join(str(item) for item in images))


if __name__ == "__main__":
    raise SystemExit(main())
