import os
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)

app = FastAPI(title="Mock IT Admin Panel")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "dev-session-secret"),
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "password")

# In-memory user store for demo purposes.
USERS: List[Dict[str, str]] = [
    {"email": "john@company.com", "role": "user", "password": "Initial#123"},
    {"email": "ops@company.com", "role": "admin", "password": "Initial#123"},
]


def get_user(email: str) -> Optional[Dict[str, str]]:
    for user in USERS:
        if user["email"].lower() == email.lower():
            return user
    return None


def require_login(request: Request) -> Optional[RedirectResponse]:
    if not request.session.get("logged_in"):
        return RedirectResponse(url="/", status_code=303)
    return None


@app.get("/", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["logged_in"] = True
        return RedirectResponse(url="/dashboard", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid username or password."},
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    message = request.query_params.get("message", "")
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "users": USERS,
            "message": message,
        },
    )


@app.post("/users/reset-password")
def reset_password(request: Request, email: str = Form(...)):
    redirect = require_login(request)
    if redirect:
        return redirect

    user = get_user(email)
    if user is None:
        message = f"User not found: {email}"
    else:
        user["password"] = "Temp#1234"
        message = f"Password reset for {email}"

    return RedirectResponse(url=f"/users?message={quote_plus(message)}", status_code=303)


@app.post("/users/delete")
def delete_user(request: Request, email: str = Form(...)):
    redirect = require_login(request)
    if redirect:
        return redirect

    user = get_user(email)
    if user is None:
        message = f"User not found: {email}"
    else:
        USERS.remove(user)
        message = f"Deleted user {email}"

    return RedirectResponse(url=f"/users?message={quote_plus(message)}", status_code=303)


@app.get("/users/create", response_class=HTMLResponse)
def create_user_page(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    message = request.query_params.get("message", "")
    return templates.TemplateResponse(
        "create_user.html",
        {
            "request": request,
            "message": message,
        },
    )


@app.post("/users/create")
def create_user(request: Request, email: str = Form(...), role: str = Form(...)):
    redirect = require_login(request)
    if redirect:
        return redirect

    normalized_role = role.lower()
    if normalized_role not in {"admin", "user"}:
        normalized_role = "user"

    if get_user(email) is not None:
        message = f"User already exists: {email}"
    else:
        USERS.append(
            {
                "email": email,
                "role": normalized_role,
                "password": "Initial#123",
            }
        )
        message = f"Created user {email} with role {normalized_role}"

    return RedirectResponse(url=f"/users?message={quote_plus(message)}", status_code=303)
