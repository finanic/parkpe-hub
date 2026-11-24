"""SQLite persistence for auth.server. Tokens and backup codes are stored only as hashes."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path

from auth.security import (
    IP_MAX_FAILS,
    IP_WINDOW,
    LOCK_SECONDS,
    MAX_FAILS,
    hash_backup,
    hash_password,
    new_backup_codes,
    token_hash,
    verify_password,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  mfa_secret TEXT,
  mfa_enabled INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  locked_until INTEGER,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  refresh_hash TEXT NOT NULL UNIQUE,
  family_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER,
  replaced_by TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS access_tokens (
  token_hash TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER
);
CREATE TABLE IF NOT EXISTS challenges (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER
);
CREATE TABLE IF NOT EXISTS backup_codes (
  code_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  used_at INTEGER
);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip TEXT NOT NULL,
  email TEXT NOT NULL,
  at INTEGER NOT NULL,
  ok INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  event TEXT NOT NULL,
  ip TEXT,
  at INTEGER NOT NULL
);
"""


class Store:
    def __init__(self, path: Path, scrypt_n: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.scrypt_n = scrypt_n
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)
        self._db.commit()
        try:
            path.chmod(0o600)
        except OSError:
            pass
        self._dummy = hash_password(uuid.uuid4().hex, n=scrypt_n)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def audit(self, event: str, ip: str, user_id: str | None = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO audit (user_id, event, ip, at) VALUES (?, ?, ?, ?)",
                (user_id, event, ip, int(time.time())),
            )
            self._db.commit()

    def ip_blocked(self, ip: str) -> bool:
        cutoff = int(time.time()) - IP_WINDOW
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM attempts WHERE ip = ? AND ok = 0 AND at > ?",
                (ip, cutoff),
            ).fetchone()
        return int(row["n"]) >= IP_MAX_FAILS

    def note_attempt(self, ip: str, email: str, ok: bool) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO attempts (ip, email, at, ok) VALUES (?, ?, ?, ?)",
                (ip, email, int(time.time()), 1 if ok else 0),
            )
            self._db.commit()

    def operator_exists(self) -> bool:
        with self._lock:
            row = self._db.execute("SELECT 1 FROM users WHERE role = 'operator' LIMIT 1").fetchone()
        return row is not None

    def user_by_email(self, email: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def user_by_id(self, user_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def create_user(self, email: str, password: str, role: str) -> bool:
        """Return False when the email already exists. Always spends a password hash."""
        digest = hash_password(password, n=self.scrypt_n)
        with self._lock:
            exists = self._db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                return False
            try:
                self._db.execute(
                    "INSERT INTO users (id, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), email, role, digest, int(time.time())),
                )
                self._db.commit()
            except sqlite3.IntegrityError:
                return False
        return True

    def check_password(self, user: sqlite3.Row | None, password: str) -> bool:
        stored = user["password_hash"] if user else self._dummy
        return verify_password(password, stored) and user is not None

    def register_failure(self, user: sqlite3.Row) -> None:
        now = int(time.time())
        count = int(user["failed_count"]) + 1
        locked = now + LOCK_SECONDS if count >= MAX_FAILS else None
        with self._lock:
            self._db.execute(
                "UPDATE users SET failed_count = ?, locked_until = ? WHERE id = ?",
                (count, locked, user["id"]),
            )
            self._db.commit()

    def clear_failures(self, user_id: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE users SET failed_count = 0, locked_until = NULL WHERE id = ?",
                (user_id,),
            )
            self._db.commit()

    def locked(self, user: sqlite3.Row | None) -> bool:
        if not user or not user["locked_until"]:
            return False
        return int(user["locked_until"]) > int(time.time())

    def save_session(self, user_id: str, refresh: str, scope: str, expires_at: int, family_id: str | None = None) -> str:
        session_id = str(uuid.uuid4())
        family = family_id or str(uuid.uuid4())
        with self._lock:
            self._db.execute(
                """INSERT INTO sessions
                   (id, user_id, refresh_hash, family_id, scope, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, token_hash(refresh), family, scope, expires_at, int(time.time())),
            )
            self._db.commit()
        return session_id

    def save_access(self, token: str, session_id: str, user_id: str, scope: str, expires_at: int) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO access_tokens (token_hash, session_id, user_id, scope, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (token_hash(token), session_id, user_id, scope, expires_at),
            )
            self._db.commit()

    def access_session(self, token: str) -> sqlite3.Row | None:
        now = int(time.time())
        with self._lock:
            return self._db.execute(
                """SELECT * FROM access_tokens
                   WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?""",
                (token_hash(token), now),
            ).fetchone()

    def revoke_access(self, token: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE access_tokens SET revoked_at = ? WHERE token_hash = ?",
                (int(time.time()), token_hash(token)),
            )
            self._db.commit()

    def rotate_refresh(self, refresh: str, new_refresh: str, expires_at: int) -> sqlite3.Row | None:
        """Return the new session row, or None. Reuse of a retired refresh kills the family."""
        now = int(time.time())
        digest = token_hash(refresh)
        with self._lock:
            row = self._db.execute("SELECT * FROM sessions WHERE refresh_hash = ?", (digest,)).fetchone()
            if not row:
                return None
            if row["revoked_at"] or row["replaced_by"] or int(row["expires_at"]) <= now:
                self._db.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
                    (now, row["family_id"]),
                )
                self._db.execute(
                    """UPDATE access_tokens SET revoked_at = ?
                       WHERE session_id IN (SELECT id FROM sessions WHERE family_id = ?)
                       AND revoked_at IS NULL""",
                    (now, row["family_id"]),
                )
                self._db.commit()
                return None
            session_id = str(uuid.uuid4())
            self._db.execute(
                "UPDATE sessions SET revoked_at = ?, replaced_by = ? WHERE id = ?",
                (now, session_id, row["id"]),
            )
            self._db.execute(
                """INSERT INTO sessions
                   (id, user_id, refresh_hash, family_id, scope, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, row["user_id"], token_hash(new_refresh), row["family_id"], row["scope"], expires_at, now),
            )
            self._db.commit()
            return self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def revoke_session_family(self, session_id: str) -> None:
        now = int(time.time())
        with self._lock:
            row = self._db.execute("SELECT family_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return
            self._db.execute(
                "UPDATE sessions SET revoked_at = ? WHERE family_id = ? AND revoked_at IS NULL",
                (now, row["family_id"]),
            )
            self._db.execute(
                """UPDATE access_tokens SET revoked_at = ?
                   WHERE session_id IN (SELECT id FROM sessions WHERE family_id = ?)
                   AND revoked_at IS NULL""",
                (now, row["family_id"]),
            )
            self._db.commit()

    def revoke_user(self, user_id: str) -> None:
        now = int(time.time())
        with self._lock:
            self._db.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            self._db.execute(
                "UPDATE access_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            self._db.commit()

    def save_challenge(self, token: str, user_id: str, expires_at: int) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO challenges (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash(token), user_id, expires_at),
            )
            self._db.commit()

    def peek_challenge(self, token: str) -> sqlite3.Row | None:
        now = int(time.time())
        with self._lock:
            return self._db.execute(
                "SELECT * FROM challenges WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (token_hash(token), now),
            ).fetchone()

    def use_challenge(self, token: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE challenges SET used_at = ? WHERE token_hash = ?",
                (int(time.time()), token_hash(token)),
            )
            self._db.commit()

    def stage_mfa(self, user_id: str, secret: str) -> list[str]:
        codes = new_backup_codes()
        with self._lock:
            self._db.execute(
                "UPDATE users SET mfa_secret = ?, mfa_enabled = 0 WHERE id = ?",
                (secret, user_id),
            )
            self._db.execute("DELETE FROM backup_codes WHERE user_id = ?", (user_id,))
            self._db.executemany(
                "INSERT INTO backup_codes (code_hash, user_id) VALUES (?, ?)",
                [(hash_backup(code), user_id) for code in codes],
            )
            self._db.commit()
        return codes

    def enable_mfa(self, user_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE users SET mfa_enabled = 1 WHERE id = ?", (user_id,))
            self._db.commit()

    def use_backup(self, user_id: str, code: str) -> bool:
        digest = hash_backup(code)
        now = int(time.time())
        with self._lock:
            row = self._db.execute(
                "SELECT code_hash FROM backup_codes WHERE user_id = ? AND code_hash = ? AND used_at IS NULL",
                (user_id, digest),
            ).fetchone()
            if not row:
                return False
            self._db.execute(
                "UPDATE backup_codes SET used_at = ? WHERE code_hash = ?",
                (now, digest),
            )
            self._db.commit()
        return True
