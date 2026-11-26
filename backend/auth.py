from uuid import UUID

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import setting

bearer = HTTPBearer(auto_error=False)


async def user(token: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not token or token.scheme.lower() != "bearer":
        raise HTTPException(401, "Sign in to access your workspace.")
    if not setting("SUPABASE_URL") or not setting("SUPABASE_PUBLISHABLE_KEY"):
        raise HTTPException(503, "Configure Supabase Auth in backend/.env.")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                setting("SUPABASE_URL").rstrip("/") + "/auth/v1/user",
                headers={
                    "apikey": setting("SUPABASE_PUBLISHABLE_KEY"),
                    "Authorization": "Bearer " + token.credentials,
                },
            )
        if response.status_code in (401, 403):
            raise HTTPException(401, "Session expired. Sign in again.")
        response.raise_for_status()
        return UUID(response.json()["id"])
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(503, "Authentication service unavailable.")
