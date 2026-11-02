#!/usr/bin/env python3
"""
Password gate for Contract Explorer.

Stateless, serverless-friendly access control:
- The access password is read from the APP_PASSWORD environment variable.
- Successful sign-on issues an HMAC-signed session cookie (expiry + signature).
- A middleware guards every route: unauthenticated page requests are
  redirected to the login page, /api/* requests receive a 401.

No server-side session store is required, so this works unchanged on
Vercel serverless functions.
"""

import asyncio
import hashlib
import hmac
import os
import time
import urllib.parse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

SESSION_COOKIE = "contract_explorer_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
FAILED_SIGNON_DELAY_SECONDS = 0.25  # blunts brute-force attempts

# Paths served without a session cookie
PUBLIC_PATHS = {"/auth/login", "/auth/logout"}


def access_password() -> str:
    return os.getenv("APP_PASSWORD", "")


def _session_key() -> bytes:
    # Derived from the access password so rotating APP_PASSWORD also
    # invalidates every previously issued session cookie.
    return hashlib.sha256(
        ("contract-explorer-session-v1:" + access_password()).encode("utf-8")
    ).digest()


def _sign(payload: str) -> str:
    return hmac.new(_session_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_session_token() -> str:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"exp={expires}"
    return f"{payload}.{_sign(payload)}"


def session_is_valid(request: Request) -> bool:
    if not access_password():
        return False
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token or "." not in token:
        return False
    payload, _, signature = token.rpartition(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return False
    if not payload.startswith("exp="):
        return False
    try:
        expires = int(payload[len("exp="):])
    except ValueError:
        return False
    return time.time() < expires


def password_matches(candidate: str) -> bool:
    expected = access_password()
    if not expected:
        return False
    return hmac.compare_digest(
        hashlib.sha256(candidate.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


def _is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


# ── Login Page ────────────────────────────────────────────────────────────────
def _login_page(show_error: bool) -> str:
    error_html = (
        '<p class="login-error">Incorrect password. Please try again.</p>'
        if show_error
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sign in | Contract Explorer</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
      background: #0b0d10;
      color: #e8eaf0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .login-card {{
      width: 100%;
      max-width: 400px;
      background: #11141a;
      border: 1px solid #23272f;
      border-radius: 12px;
      padding: 40px 36px;
    }}
    .login-brand {{
      font-size: 1.35rem;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .login-brand span {{ color: #f59e0b; }}
    .login-subtitle {{
      color: #8b93a3;
      font-size: 0.9rem;
      margin-bottom: 28px;
    }}
    .login-error {{
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #f87171;
      font-size: 0.85rem;
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 18px;
    }}
    label {{
      display: block;
      font-size: 0.82rem;
      font-weight: 500;
      color: #a8b0bf;
      margin-bottom: 8px;
    }}
    input[type="password"] {{
      width: 100%;
      background: #0b0d10;
      border: 1px solid #23272f;
      border-radius: 8px;
      color: #e8eaf0;
      font-size: 0.95rem;
      font-family: inherit;
      padding: 12px 14px;
      margin-bottom: 20px;
      outline: none;
    }}
    input[type="password"]:focus {{ border-color: #f59e0b; }}
    button {{
      width: 100%;
      background: #f59e0b;
      color: #0b0d10;
      border: none;
      border-radius: 8px;
      font-family: inherit;
      font-size: 0.95rem;
      font-weight: 600;
      padding: 12px;
      cursor: pointer;
    }}
    button:hover {{ background: #fbbf24; }}
    .login-footer {{
      color: #5c6470;
      font-size: 0.78rem;
      text-align: center;
      margin-top: 26px;
    }}
  </style>
</head>
<body>
  <div class="login-card">
    <div class="login-brand"><span>Contract</span>Explorer</div>
    <div class="login-subtitle">Access to this workspace is restricted. Please sign in to continue.</div>
    {error_html}
    <form method="POST" action="/auth/login">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" autofocus autocomplete="current-password" required>
      <button type="submit">Sign in</button>
    </form>
    <div class="login-footer">Contract Explorer &mdash; UK Energy Subsidy Terms</div>
  </div>
</body>
</html>"""


# ── Auth Routes ───────────────────────────────────────────────────────────────
async def login_page(request: Request):
    if session_is_valid(request):
        return RedirectResponse("/", status_code=303)
    show_error = request.query_params.get("error") == "1"
    return HTMLResponse(
        content=_login_page(show_error),
        headers={"Cache-Control": "no-store"},
    )


async def login_submit(request: Request):
    body = await request.body()
    form = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    candidate = (form.get("password") or [""])[0]
    if not password_matches(candidate):
        await asyncio.sleep(FAILED_SIGNON_DELAY_SECONDS)
        return RedirectResponse("/auth/login?error=1", status_code=303)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        issue_session_token(),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )
    return response


async def logout():
    response = RedirectResponse("/auth/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── Guard Middleware ──────────────────────────────────────────────────────────
class AuthGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not access_password():
            return JSONResponse(
                {"detail": "Server misconfigured: APP_PASSWORD is not set."},
                status_code=503,
            )
        path = request.url.path
        if path in PUBLIC_PATHS or session_is_valid(request):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated."}, status_code=401)
        return RedirectResponse("/auth/login", status_code=303)


def register_auth(app: FastAPI) -> None:
    """Attach the guard middleware and auth routes to the FastAPI app."""
    app.add_middleware(AuthGuardMiddleware)
    app.get("/auth/login", include_in_schema=False)(login_page)
    app.post("/auth/login", include_in_schema=False)(login_submit)
    app.get("/auth/logout", include_in_schema=False)(logout)
