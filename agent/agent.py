import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from browser import BrowserController
from planner import Planner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)


def run_task(task: str, base_url: str, headless: bool, max_steps: int) -> None:
    planner = Planner()
    intent = planner.parse_intent(task)

    print(f"Task: {task}")
    print(f"Parsed Intent: {json.dumps(intent, ensure_ascii=True)}")

    credentials = {
        "username": os.getenv("ADMIN_USERNAME", "admin"),
        "password": os.getenv("ADMIN_PASSWORD", "password"),
        "base_url": base_url,
    }

    browser = BrowserController(headless=headless)
    browser.start()

    history = []

    try:
        for step_index in range(1, max_steps + 1):
            state = browser.snapshot()
            plan = planner.next_step(
                task=task,
                intent=intent,
                history=history,
                state=state,
                credentials=credentials,
            )

            thought = plan.get("thought", "")
            action = plan.get("action", "done")
            action_input = plan.get("action_input", "")

            print(f"\nStep {step_index}")
            print(f"Thought: {thought}")
            print(f"Action: {action}")
            if isinstance(action_input, (dict, list)):
                print(f"Action Input: {json.dumps(action_input, ensure_ascii=True)}")
            else:
                print(f"Action Input: {action_input}")

            if action == "done":
                print(f"Observation: {action_input}")
                break

            try:
                if isinstance(action_input, list):
                    executable_input = json.dumps(action_input, ensure_ascii=True)
                elif isinstance(action_input, dict):
                    executable_input = action_input
                elif isinstance(action_input, str):
                    executable_input = action_input
                else:
                    executable_input = str(action_input)
                observation = browser.execute(action, executable_input)
            except Exception as exc:
                observation = f"ERROR: {exc}"

            print(f"Observation: {observation}")

            history.append(
                {
                    "thought": thought,
                    "action": action,
                    "action_input": action_input,
                    "observation": observation,
                }
            )
        else:
            print("Observation: Reached max steps without completion.")
    finally:
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Natural-language IT support browser agent")
    parser.add_argument("--task", required=True, help="Natural language support request")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Mock admin panel base URL",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="Maximum ReAct iterations",
    )

    args = parser.parse_args()
    run_task(
        task=args.task,
        base_url=args.base_url,
        headless=args.headless,
        max_steps=args.max_steps,
    )


if __name__ == "__main__":
    main()
