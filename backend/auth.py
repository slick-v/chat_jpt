import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Annotated



import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from backend import db
from backend.config import settings

password_hash = PasswordHash.recommended()  # argon2

# Checked against when the username doesn't exist, so login takes the same time either way
# and response timing doesn't reveal which usernames are registered

_DUMMY_HASH = password_hash.hash("dummy-password")

# Tells FastAPI (and the /docs Authorize button) where tokens come from
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _credentials_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers = {"www-Authenticate": "Bearer"}
    )

def create_user(username: str, password: str) -> dict | None:
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash.hash(password)),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # username already taken (UNIQUE constraint)
    return {"id": user_id, "username": username}



def authenticate(username: str, password: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if row is None:
        password_hash.verify(password, _DUMMY_HASH)
        return None
    if not password_hash.verify(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"]}



def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expires}  # PyJWT requires "sub" to be a string
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)



def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    try:
        # Always pass algorithms explicitly, so a forged token can't pick its own (e.g. "none")
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise _credentials_error() from None

    with db.connect() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:  # user was deleted after the token was issued
        raise _credentials_error()
    return {"id": row["id"], "username": row["username"]}


# Add `user: CurrentUser` to any route to make it require login
CurrentUser = Annotated[dict, Depends(get_current_user)]