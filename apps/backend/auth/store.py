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
CREATE TABLE IF NOT EXISTS memberships (
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  PRIMARY KEY (user_id, role)
);
CREATE TABLE IF NOT EXISTS signup_intents (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  mobile TEXT NOT NULL,
  role TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  user_id TEXT,
  email_code_hash TEXT NOT NULL,
  sms_code_hash TEXT NOT NULL,
  email_ok INTEGER NOT NULL DEFAULT 0,
  mobile_ok INTEGER NOT NULL DEFAULT 0,
  aadhaar_ok INTEGER NOT NULL DEFAULT 0,
  pan_ok INTEGER NOT NULL DEFAULT 0,
  aadhaar_ref TEXT,
  live INTEGER NOT NULL DEFAULT 0,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
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
        self._ensure_column("sessions", "role", "TEXT")
        self._ensure_column("access_tokens", "role", "TEXT")
        self._ensure_column("challenges", "role", "TEXT")
        self._ensure_column("users", "sign_in", "INTEGER NOT NULL DEFAULT 1")
        self._rename_operator_role()
        self._db.execute(
            "INSERT OR IGNORE INTO memberships (user_id, role) SELECT id, role FROM users"
        )
        self._db.commit()
        try:
            path.chmod(0o600)
        except OSError:
            pass
        self._dummy = hash_password(uuid.uuid4().hex, n=scrypt_n)

    def _ensure_column(self, table: str, column: str, typedef: str) -> None:
        found = [row[1] for row in self._db.execute(f"PRAGMA table_info({table})")]
        if column not in found:
            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")

    def _rename_operator_role(self) -> None:
        """The desk role is admin. Rows written as operator become admin."""
        for table in ("users", "memberships", "sessions", "access_tokens", "challenges", "signup_intents"):
            self._db.execute(f"UPDATE {table} SET role = 'admin' WHERE role = 'operator'")
        self._db.commit()

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

    def membership_counts(self) -> dict[str, int]:
        counts = {"customer": 0, "retailer": 0, "admin": 0}
        with self._lock:
            rows = self._db.execute(
                "SELECT role, COUNT(*) AS n FROM memberships GROUP BY role"
            ).fetchall()
        for row in rows:
            if row["role"] in counts:
                counts[row["role"]] = int(row["n"])
        return counts

    def recent_audit(self, limit: int = 8) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT a.event, a.at, u.email
                   FROM audit a
                   LEFT JOIN users u ON u.id = a.user_id
                   ORDER BY a.id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {"event": row["event"], "at": int(row["at"]), "email": row["email"] or ""}
            for row in rows
        ]

    def list_people(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT u.email, u.mfa_enabled, u.sign_in, GROUP_CONCAT(m.role) AS roles
                   FROM users u
                   LEFT JOIN memberships m ON m.user_id = u.id
                   GROUP BY u.id
                   ORDER BY u.email"""
            ).fetchall()
        people = []
        for row in rows:
            roles = sorted({part for part in (row["roles"] or "").split(",") if part})
            people.append(
                {
                    "email": row["email"],
                    "roles": roles,
                    "authenticator": bool(row["mfa_enabled"]),
                    "sign_in": bool(row["sign_in"]),
                }
            )
        return people

    def set_sign_in(self, user_id: str, enabled: bool) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE users SET sign_in = ? WHERE id = ?",
                (1 if enabled else 0, user_id),
            )
            self._db.commit()
        if not enabled:
            self.revoke_user(user_id)

    def open_operator_count(self) -> int:
        with self._lock:
            row = self._db.execute(
                """SELECT COUNT(*) AS n FROM users u
                   JOIN memberships m ON m.user_id = u.id AND m.role = 'admin'
                   WHERE u.sign_in = 1"""
            ).fetchone()
        return int(row["n"])

    def recent_signups(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT email, mobile, role, email_ok, mobile_ok, aadhaar_ok, pan_ok,
                          expires_at, created_at
                   FROM signup_intents
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        listed = []
        for row in rows:
            digits = "".join(ch for ch in (row["mobile"] or "") if ch.isdigit())
            listed.append(
                {
                    "email": row["email"],
                    "mobile_last4": digits[-4:] if len(digits) >= 4 else "",
                    "role": row["role"],
                    "email_ok": bool(row["email_ok"]),
                    "mobile_ok": bool(row["mobile_ok"]),
                    "aadhaar_ok": bool(row["aadhaar_ok"]),
                    "pan_ok": bool(row["pan_ok"]),
                    "open": int(row["expires_at"]) > int(time.time()),
                    "created_at": int(row["created_at"]),
                }
            )
        return listed

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
            row = self._db.execute(
                "SELECT 1 FROM memberships WHERE role = 'admin' LIMIT 1"
            ).fetchone()
        return row is not None

    def has_membership(self, user_id: str, role: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM memberships WHERE user_id = ? AND role = ?",
                (user_id, role),
            ).fetchone()
        return row is not None

    def add_membership(self, user_id: str, role: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO memberships (user_id, role) VALUES (?, ?)",
                (user_id, role),
            )
            self._db.commit()

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
                user_id = str(uuid.uuid4())
                self._db.execute(
                    "INSERT INTO users (id, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, email, role, digest, int(time.time())),
                )
                self._db.execute(
                    "INSERT OR IGNORE INTO memberships (user_id, role) VALUES (?, ?)",
                    (user_id, role),
                )
                self._db.commit()
            except sqlite3.IntegrityError:
                return False
        return True

    def create_user_with_hash(self, email: str, digest: str, role: str) -> bool:
        """Insert a verified account. False when that email already exists."""
        with self._lock:
            exists = self._db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
            if exists:
                return False
            user_id = str(uuid.uuid4())
            self._db.execute(
                "INSERT INTO users (id, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, email, role, digest, int(time.time())),
            )
            self._db.execute(
                "INSERT OR IGNORE INTO memberships (user_id, role) VALUES (?, ?)",
                (user_id, role),
            )
            self._db.commit()
        return True

    def save_signup(self, row: dict) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO signup_intents
                   (id, email, mobile, role, password_hash, user_id, email_code_hash, sms_code_hash,
                    live, aadhaar_ref, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"],
                    row["email"],
                    row["mobile"],
                    row["role"],
                    row["password_hash"],
                    row.get("user_id"),
                    row["email_code_hash"],
                    row["sms_code_hash"],
                    1 if row.get("live") else 0,
                    row.get("aadhaar_ref"),
                    row["expires_at"],
                    row["created_at"],
                ),
            )
            self._db.commit()

    def signup(self, signup_id: str) -> sqlite3.Row | None:
        now = int(time.time())
        with self._lock:
            return self._db.execute(
                "SELECT * FROM signup_intents WHERE id = ? AND expires_at > ?",
                (signup_id, now),
            ).fetchone()

    def mark_signup(self, signup_id: str, **fields) -> None:
        if not fields:
            return
        allowed = {"email_ok", "mobile_ok", "aadhaar_ok", "pan_ok", "aadhaar_ref"}
        keys = [key for key in fields if key in allowed]
        if not keys:
            return
        assignments = ", ".join(f"{key} = ?" for key in keys)
        with self._lock:
            self._db.execute(
                f"UPDATE signup_intents SET {assignments} WHERE id = ?",
                [fields[key] for key in keys] + [signup_id],
            )
            self._db.commit()

    def delete_signup(self, signup_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM signup_intents WHERE id = ?", (signup_id,))
            self._db.commit()

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

    def save_session(self, user_id: str, refresh: str, scope: str, expires_at: int, family_id: str | None = None, role: str = "") -> str:
        session_id = str(uuid.uuid4())
        family = family_id or str(uuid.uuid4())
        with self._lock:
            self._db.execute(
                """INSERT INTO sessions
                   (id, user_id, refresh_hash, family_id, scope, expires_at, created_at, role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, token_hash(refresh), family, scope, expires_at, int(time.time()), role),
            )
            self._db.commit()
        return session_id

    def save_access(self, token: str, session_id: str, user_id: str, scope: str, expires_at: int, role: str = "") -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO access_tokens (token_hash, session_id, user_id, scope, expires_at, role)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (token_hash(token), session_id, user_id, scope, expires_at, role),
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
                   (id, user_id, refresh_hash, family_id, scope, expires_at, created_at, role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    row["user_id"],
                    token_hash(new_refresh),
                    row["family_id"],
                    row["scope"],
                    expires_at,
                    now,
                    row["role"] if "role" in row.keys() else "",
                ),
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

    def save_challenge(self, token: str, user_id: str, expires_at: int, role: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO challenges (token_hash, user_id, expires_at, role) VALUES (?, ?, ?, ?)",
                (token_hash(token), user_id, expires_at, role),
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
