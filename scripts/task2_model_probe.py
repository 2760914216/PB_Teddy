from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Ollama candidate model for Task2"
    )
    parser.add_argument("--config", default="config.yaml", help="Task2 config path")
    parser.add_argument("--model", required=True, help="Candidate Ollama model name")
    args = parser.parse_args()

    config_module = importlib.import_module("src.task2.config")
    llm_module = importlib.import_module("src.task2.llm_client")
    prompt_module = importlib.import_module("src.task2.prompts_nl2sql")
    cases_module = importlib.import_module("src.task2.probe_cases")

    load_task2_config = getattr(config_module, "load_task2_config")
    llm_client_class = getattr(llm_module, "Task2LLMClient")
    build_probe_prompt = getattr(prompt_module, "build_probe_prompt")
    probe_cases = getattr(cases_module, "PROBE_CASES")

    config = load_task2_config(args.config)
    client = llm_client_class(config, model_override=args.model)
    verdicts: list[str] = []
    for case in probe_cases:
        question_id = str(case["question_id"])
        question = str(case["question"])
        system_prompt, user_prompt = build_probe_prompt(question_id, question)
        try:
            result = client.chat_json(system_prompt, user_prompt)
            parseable = isinstance(result, dict)
            sql = str(result.get("sql") or "")
            analysis = str(result.get("analysis") or "")
            recommended = (
                "yes"
                if parseable and sql.startswith("SELECT") and bool(analysis.strip())
                else "no"
            )
            verdicts.append(
                f"{question_id} parseable={'yes' if parseable else 'no'} recommended={recommended} sql={json.dumps(sql, ensure_ascii=False)}"
            )
        except Exception as exc:  # noqa: BLE001
            verdicts.append(f"{question_id} parseable=no recommended=no error={exc}")

    output = "\n".join(verdicts)
    print(output)
    return 0 if any("recommended=yes" in line for line in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
