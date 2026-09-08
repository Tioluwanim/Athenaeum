"""
app/auth.py — Firebase Authentication, verified server-side.

Supersedes the JWT-based scheme from the first pass of this rebuild
(custom email/password + hand-rolled JWTs). That design is gone entirely:
Firebase now owns identity (Google sign-in, email/password, password
reset, email verification), and FastAPI's only job is to verify the
ID token Firebase issued — it NEVER trusts a user id supplied directly
by the frontend.

Split of responsibility:
  - Firebase: authentication (who is this person, is their email verified)
  - Local `users` table: authorization (are they "admin" or "staff" in
    THIS library's system) — a Firebase account alone doesn't grant any
    role; an admin has to be provisioned (see provision_user below).

Every request that needs a user calls `get_current_user`, which:
  1. Reads the `Authorization: Bearer <firebase_id_token>` header
  2. Verifies it against Firebase's public keys via firebase_admin
     (signature, expiry, issuer, audience — all checked by the SDK)
  3. Looks up (or lazily creates, on first sign-in) the matching row in
     the local `users` table by email
  4. Returns a CurrentUser built from THAT row's role, not from anything
     the client sent
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.db.models import User
from app.db.session import get_session
from app.utils.logger import get_logger

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)

_firebase_app = None


def _init_firebase():
    """Lazy init so importing this module doesn't require Firebase
    credentials to be present (e.g. during `alembic upgrade head`)."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    import os
    import firebase_admin
    from firebase_admin import credentials

    cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()

    if cred_json:
        import json
        cred = credentials.Certificate(json.loads(cred_json))
    elif cred_path:
        cred = credentials.Certificate(cred_path)
    else:
        # Works out of the box on GCP/Cloud Run; elsewhere one of the two
        # env vars above is required.
        cred = credentials.ApplicationDefault()

    _firebase_app = firebase_admin.initialize_app(cred)
    logger.info("Firebase Admin SDK initialised")
    return _firebase_app


class CurrentUser(BaseModel):
    id: int                  # local users.id (authorization identity)
    firebase_uid: str
    email: str
    full_name: str
    role: str                 # "admin" | "staff" — set locally, NEVER by the client
    email_verified: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _verify_firebase_token(id_token: str) -> dict:
    from firebase_admin import auth as firebase_auth

    _init_firebase()
    try:
        # check_revoked=True adds a lookup but rejects a disabled/revoked
        # account immediately rather than waiting for next token refresh —
        # worth it for a library staff tool with admin-managed accounts.
        return firebase_auth.verify_id_token(id_token, check_revoked=True)
    except firebase_auth.RevokedIdTokenError:
        raise HTTPException(status_code=401, detail="Session revoked, please sign in again")
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Session expired, please sign in again")
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    except Exception as e:  # noqa: BLE001
        logger.error("Firebase token verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Could not verify authentication token")


def _get_or_provision_user(decoded: dict) -> CurrentUser:
    """First sign-in creates a local `users` row with role='staff' by
    default. Promotion to 'admin' happens out-of-band (an existing admin
    changes the role via /api/admin/users, or ADMIN_INVITE_CODE is used
    at first registration — see api_main.py) — a Firebase token alone
    never grants admin."""
    uid = decoded["uid"]
    email = decoded.get("email", "")
    name = decoded.get("name", "") or (email.split("@")[0] if email else uid)
    email_verified = bool(decoded.get("email_verified", False))

    with get_session() as session:
        from sqlalchemy import select
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()

        if user is None:
            user = User(
                email=email,
                password_hash="firebase",  # unused — Firebase owns credentials
                full_name=name,
                role="staff",
                is_active=1,
                created_at=datetime.utcnow(),
                last_login_at=datetime.utcnow(),
            )
            session.add(user)
            session.flush()
            logger.info("Provisioned new local user for %s (firebase uid=%s)", email, uid)
        else:
            user.last_login_at = datetime.utcnow()

        session.commit()

        if not user.is_active:
            raise HTTPException(status_code=401, detail="Account has been deactivated")

        return CurrentUser(
            id=user.id, firebase_uid=uid, email=user.email, full_name=user.full_name,
            role=user.role, email_verified=email_verified,
        )


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    decoded = _verify_firebase_token(creds.credentials)
    return _get_or_provision_user(decoded)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an admin account",
        )
    return user


def require_verified_email(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before continuing",
        )
    return user
