# AI IT Support Browser Agent (FastAPI + Playwright)

This project includes:
- A mock IT admin panel built with FastAPI.
- A Python AI agent that converts natural-language requests into structured intent.
- A ReAct-style action loop (Thought -> Action -> Observation).
- Browser execution via Playwright using human-like interactions (visible text, button labels, placeholders).

## Project Structure

project-root/
- backend/
  - app.py
  - templates/
    - login.html
    - dashboard.html
    - users.html
    - create_user.html
- agent/
  - agent.py
  - planner.py
  - browser.py
- prompts/
  - system_prompt.txt
- .env
- requirements.txt
- README.md

## Prerequisites

- Python 3.10+
- A valid OpenAI API key

## Setup

1. Create and activate a virtual environment.

Windows PowerShell:

python -m venv .venv
.\.venv\Scripts\Activate.ps1

2. Install dependencies.

pip install -r requirements.txt

3. Install Playwright browser.

playwright install chromium

4. Update environment values in .env.

Required values:
- OPENAI_API_KEY
- ADMIN_USERNAME
- ADMIN_PASSWORD
- SESSION_SECRET

## Run the Backend

From project root:

uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000

Open:
- http://127.0.0.1:8000

## Run the Agent

Open a second terminal in project root and run:

python agent/agent.py --task "Reset password for john@company.com"

Example 2:

python agent/agent.py --task "Create user alice@company.com with admin role"

Bonus example:

python agent/agent.py --task "If user does not exist, create it, then reset password for sam@company.com"

Optional flags:
- --base-url http://127.0.0.1:8000
- --headless
- --max-steps 30

## Demo Tasks Covered

1. Reset password for john@company.com
2. Create user alice@company.com with admin role

The agent logs each iteration as:
- Thought: ...
- Action: ...
- Action Input: ...
- Observation: ...

## Notes

- Users are stored in memory only (reset when backend restarts).
- The planner uses OpenAI when OPENAI_API_KEY is set.
- If no API key is present, a built-in rule-based planner still executes the required demo flows.
# AI-Agent
