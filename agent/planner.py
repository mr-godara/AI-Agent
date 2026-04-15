from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)

ALLOWED_ACTIONS = {"navigate", "click", "type", "read", "wait", "done"}


class Planner:
    def __init__(self, prompt_path: Optional[str] = None, model: Optional[str] = None):
        base_dir = Path(__file__).resolve().parents[1]
        prompt_file = Path(prompt_path) if prompt_path else base_dir / "prompts" / "system_prompt.txt"

        self.system_prompt = prompt_file.read_text(encoding="utf-8")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.client = OpenAI(api_key=api_key) if api_key else None

    def parse_intent(self, task: str) -> Dict[str, Any]:
        if self.client is None:
            return self._heuristic_parse_intent(task)

        prompt = (
            "Convert this IT support request into strict JSON only. "
            "Schema: {\"intent\": string, \"email\": string|null, \"role\": string|null, \"condition\": string|null}. "
            "Valid intents: reset_password, create_user, ensure_user_then_reset, unknown.\n\n"
            f"Request: {task}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": "Return JSON only. No markdown. No extra text.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or "{}"
            parsed = self._extract_json(content)
            if parsed is None:
                return self._heuristic_parse_intent(task)
            return self._normalize_intent(parsed, task)
        except Exception:
            return self._heuristic_parse_intent(task)

    def next_step(
        self,
        task: str,
        intent: Dict[str, Any],
        history: List[Dict[str, Any]],
        state: Dict[str, Any],
        credentials: Dict[str, str],
    ) -> Dict[str, Any]:
        if self.client is not None:
            step = self._llm_next_step(task, intent, history, state, credentials)
            if step is not None:
                return step

        return self._rule_based_next_step(intent, history, credentials)

    def _llm_next_step(
        self,
        task: str,
        intent: Dict[str, Any],
        history: List[Dict[str, Any]],
        state: Dict[str, Any],
        credentials: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        if self.client is None:
            return None

        history_block = json.dumps(history[-8:], ensure_ascii=True)
        state_block = json.dumps(state, ensure_ascii=True)
        intent_block = json.dumps(intent, ensure_ascii=True)

        user_prompt = (
            f"Task: {task}\n"
            f"Parsed intent: {intent_block}\n"
            f"Credentials: {json.dumps(credentials, ensure_ascii=True)}\n"
            f"Current browser state: {state_block}\n"
            f"Recent history: {history_block}\n\n"
            "Return exactly:\n"
            "Thought: <short reasoning>\n"
            "Action: <one of navigate|click|type|read|wait|done>\n"
            "Action Input: <JSON object or string>"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content or ""
            return self._parse_react_output(content)
        except Exception:
            return None

    def _rule_based_next_step(
        self,
        intent: Dict[str, Any],
        history: List[Dict[str, Any]],
        credentials: Dict[str, str],
    ) -> Dict[str, Any]:
        intent_name = str(intent.get("intent", "unknown"))
        email = str(intent.get("email") or "")
        role = str(intent.get("role") or "user")

        if not self._has_action(history, "navigate"):
            return {
                "thought": "Open the admin login page first.",
                "action": "navigate",
                "action_input": {"url": credentials["base_url"]},
            }
        if not self._has_type(history, "Username"):
            return {
                "thought": "Enter login username.",
                "action": "type",
                "action_input": {"field": "Username", "value": credentials["username"]},
            }
        if not self._has_type(history, "Password"):
            return {
                "thought": "Enter login password.",
                "action": "type",
                "action_input": {"field": "Password", "value": credentials["password"]},
            }
        if not self._has_click(history, "Login"):
            return {
                "thought": "Submit login form.",
                "action": "click",
                "action_input": {"text": "Login"},
            }

        if intent_name == "create_user":
            return self._plan_create_user(history, email, role)

        if intent_name == "reset_password":
            return self._plan_reset_password(history, email)

        if intent_name == "ensure_user_then_reset":
            return self._plan_ensure_then_reset(history, email, role)

        return {
            "thought": "Task is unclear, so stop safely.",
            "action": "done",
            "action_input": {"result": f"Unsupported request: {intent_name}"},
        }

    def _plan_create_user(self, history: List[Dict[str, Any]], email: str, role: str) -> Dict[str, Any]:
        if not self._has_click(history, "Create User"):
            return {
                "thought": "Open the create user page.",
                "action": "click",
                "action_input": {"text": "Create User"},
            }
        if not self._has_type(history, "Email"):
            return {
                "thought": "Fill in the new user email.",
                "action": "type",
                "action_input": {"field": "Email", "value": email},
            }
        if not self._has_type(history, "Role"):
            return {
                "thought": "Set the requested role.",
                "action": "type",
                "action_input": {"field": "Role", "value": role},
            }
        if not self._has_click(history, "Create"):
            return {
                "thought": "Submit the create form.",
                "action": "click",
                "action_input": {"text": "Create"},
            }
        return {
            "thought": "User creation flow completed.",
            "action": "done",
            "action_input": {"result": f"Create user flow finished for {email} ({role})."},
        }

    def _plan_reset_password(self, history: List[Dict[str, Any]], email: str) -> Dict[str, Any]:
        if not self._has_click(history, "Users"):
            return {
                "thought": "Open users list first.",
                "action": "click",
                "action_input": {"text": "Users"},
            }

        if self._count_read(history, email) == 0:
            return {
                "thought": "Check whether the requested user exists.",
                "action": "read",
                "action_input": {"text": email},
            }

        if not self._last_read_found(history, email):
            return {
                "thought": "Target user was not found.",
                "action": "done",
                "action_input": {"result": f"Cannot reset password. User not found: {email}"},
            }

        button_text = f"Reset Password for {email}"
        if not self._has_click(history, button_text):
            return {
                "thought": "Click the reset button for this user.",
                "action": "click",
                "action_input": {"text": button_text},
            }

        return {
            "thought": "Password reset flow completed.",
            "action": "done",
            "action_input": {"result": f"Password reset flow finished for {email}."},
        }

    def _plan_ensure_then_reset(
        self,
        history: List[Dict[str, Any]],
        email: str,
        role: str,
    ) -> Dict[str, Any]:
        if not self._has_click(history, "Users"):
            return {
                "thought": "Open users list to check existence.",
                "action": "click",
                "action_input": {"text": "Users"},
            }

        reads = self._count_read(history, email)
        if reads == 0:
            return {
                "thought": "Verify whether the user already exists.",
                "action": "read",
                "action_input": {"text": email},
            }

        if reads == 1 and not self._last_read_found(history, email):
            if not self._has_click(history, "Create User"):
                return {
                    "thought": "User is missing, open create form.",
                    "action": "click",
                    "action_input": {"text": "Create User"},
                }
            if self._count_type_with_value(history, "Email", email) == 0:
                return {
                    "thought": "Enter missing user email.",
                    "action": "type",
                    "action_input": {"field": "Email", "value": email},
                }
            if self._count_type_with_value(history, "Role", role) == 0:
                return {
                    "thought": "Set role before creating user.",
                    "action": "type",
                    "action_input": {"field": "Role", "value": role},
                }
            if self._count_click(history, "Create") == 0:
                return {
                    "thought": "Create the missing user.",
                    "action": "click",
                    "action_input": {"text": "Create"},
                }
            if self._count_click(history, "Users") < 2:
                return {
                    "thought": "Return to users page for reset action.",
                    "action": "click",
                    "action_input": {"text": "Users"},
                }
            if reads < 2:
                return {
                    "thought": "Re-check that the new user is visible.",
                    "action": "read",
                    "action_input": {"text": email},
                }

        if reads >= 1 and self._last_read_found(history, email):
            button_text = f"Reset Password for {email}"
            if not self._has_click(history, button_text):
                return {
                    "thought": "Now reset password for the target user.",
                    "action": "click",
                    "action_input": {"text": button_text},
                }
            return {
                "thought": "Ensure-and-reset flow completed.",
                "action": "done",
                "action_input": {
                    "result": f"User ensured and password reset completed for {email}."
                },
            }

        return {
            "thought": "Could not verify user state safely.",
            "action": "done",
            "action_input": {"result": f"Flow stopped. Could not verify user: {email}"},
        }

    def _parse_react_output(self, content: str) -> Optional[Dict[str, Any]]:
        thought_match = re.search(r"Thought:\s*(.+)", content)
        action_match = re.search(r"Action:\s*(.+)", content)
        input_match = re.search(r"Action Input:\s*(.+)", content, flags=re.DOTALL)

        if not thought_match or not action_match or not input_match:
            return None

        thought = thought_match.group(1).strip()
        action = action_match.group(1).strip()
        input_text = input_match.group(1).strip()

        if action not in ALLOWED_ACTIONS:
            return None

        action_input: Any
        parsed_json = self._extract_json(input_text)
        action_input = parsed_json if parsed_json is not None else input_text

        return {
            "thought": thought,
            "action": action,
            "action_input": action_input,
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        text = text.strip()
        if not text:
            return None

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
            return None
        except json.JSONDecodeError:
            return None

    def _heuristic_parse_intent(self, task: str) -> Dict[str, Any]:
        lower = task.lower()
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", task)
        email = email_match.group(0) if email_match else None

        role = "admin" if "admin" in lower else "user"

        if "if user does not exist" in lower and "reset" in lower:
            intent = "ensure_user_then_reset"
            condition = "create_if_missing_then_reset"
        elif "create" in lower and "user" in lower:
            intent = "create_user"
            condition = None
        elif "reset" in lower and "password" in lower:
            intent = "reset_password"
            condition = None
        else:
            intent = "unknown"
            condition = None

        return {
            "intent": intent,
            "email": email,
            "role": role,
            "condition": condition,
        }

    @staticmethod
    def _normalize_intent(parsed: Dict[str, Any], task: str) -> Dict[str, Any]:
        normalized = {
            "intent": str(parsed.get("intent", "unknown")),
            "email": parsed.get("email"),
            "role": parsed.get("role") or ("admin" if "admin" in task.lower() else "user"),
            "condition": parsed.get("condition"),
        }

        if normalized["intent"] not in {
            "reset_password",
            "create_user",
            "ensure_user_then_reset",
            "unknown",
        }:
            normalized["intent"] = "unknown"

        return normalized

    @staticmethod
    def _has_action(history: List[Dict[str, Any]], action: str) -> bool:
        return any(step.get("action") == action for step in history)

    @staticmethod
    def _count_click(history: List[Dict[str, Any]], text: str) -> int:
        count = 0
        for step in history:
            if step.get("action") != "click":
                continue
            action_input = step.get("action_input")
            if isinstance(action_input, dict) and str(action_input.get("text")) == text:
                count += 1
            elif isinstance(action_input, str) and action_input == text:
                count += 1
        return count

    def _has_click(self, history: List[Dict[str, Any]], text: str) -> bool:
        return self._count_click(history, text) > 0

    @staticmethod
    def _has_type(history: List[Dict[str, Any]], field: str) -> bool:
        for step in history:
            if step.get("action") != "type":
                continue
            action_input = step.get("action_input")
            if isinstance(action_input, dict) and str(action_input.get("field")) == field:
                return True
        return False

    @staticmethod
    def _count_type_with_value(history: List[Dict[str, Any]], field: str, value: str) -> int:
        count = 0
        for step in history:
            if step.get("action") != "type":
                continue
            action_input = step.get("action_input")
            if not isinstance(action_input, dict):
                continue
            if str(action_input.get("field")) == field and str(action_input.get("value")) == value:
                count += 1
        return count

    @staticmethod
    def _count_read(history: List[Dict[str, Any]], text: str) -> int:
        count = 0
        for step in history:
            if step.get("action") != "read":
                continue
            action_input = step.get("action_input")
            if isinstance(action_input, dict) and str(action_input.get("text")) == text:
                count += 1
            elif isinstance(action_input, str) and action_input == text:
                count += 1
        return count

    @staticmethod
    def _last_read_found(history: List[Dict[str, Any]], text: str) -> bool:
        for step in reversed(history):
            if step.get("action") != "read":
                continue
            action_input = step.get("action_input")

            same_target = False
            if isinstance(action_input, dict):
                same_target = str(action_input.get("text")) == text
            elif isinstance(action_input, str):
                same_target = action_input == text

            if not same_target:
                continue

            observation = str(step.get("observation", ""))
            return observation.startswith("FOUND:")

        return False
