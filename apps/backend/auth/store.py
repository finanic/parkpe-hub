"""SQLite persistence for auth.server. Tokens and backup codes are stored only as hashes."""

from __future__ import annotations

import re
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
  email TEXT NOT NULL,
  role TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  mfa_secret TEXT,
  mfa_enabled INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  locked_until INTEGER,
  mfa_last_step INTEGER,
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
CREATE TABLE IF NOT EXISTS service_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at INTEGER NOT NULL,
  action TEXT NOT NULL,
  app_context TEXT NOT NULL DEFAULT '',
  actor TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT '',
  target_id TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL DEFAULT '',
  status INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error_code TEXT NOT NULL DEFAULT '',
  error_reason TEXT NOT NULL DEFAULT '',
  request_text TEXT NOT NULL DEFAULT '',
  response_text TEXT NOT NULL DEFAULT ''
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
  created_at INTEGER NOT NULL,
  fails INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS account_profiles (
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  mobile_last4 TEXT NOT NULL DEFAULT '',
  email_ok INTEGER NOT NULL DEFAULT 0,
  mobile_ok INTEGER NOT NULL DEFAULT 0,
  aadhaar_ok INTEGER NOT NULL DEFAULT 0,
  pan_ok INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, role)
);
"""


class Store:
    def __init__(self, path: Path, scrypt_n: int):
        path.parent.mkdir(parents=True, exist_ok=True)
        from core.privatefiles import restrict_private

        restrict_private(path.parent)
        restrict_private(path)
        self.scrypt_n = scrypt_n
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)
        self._ensure_column("sessions", "role", "TEXT")
        self._ensure_column("sessions", "device_key", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("sessions", "user_agent", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("sessions", "ip", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("access_tokens", "role", "TEXT")
        self._ensure_column("challenges", "role", "TEXT")
        self._ensure_column("challenges", "device_key", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("users", "sign_in", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column("users", "is_super", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("users", "mfa_last_step", "INTEGER")
        self._ensure_column("signup_intents", "fails", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("account_profiles", "pan_mask", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "digilocker_ref", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "pan_name_hint", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("audit", "request_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("audit", "response_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("signup_intents", "pan_mask", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("signup_intents", "pan_name_hint", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "mobile", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "pan", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "pan_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "pan_registered_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "digilocker_verification_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("service_log", "request_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("service_log", "response_text", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "display_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "outlet_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "city", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "address", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "gstin", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "udyam", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "business_legal_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "business_status", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "shop_lat", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "shop_lng", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "location_source", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "verification_ip", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("account_profiles", "business_note", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("signup_intents", "pan", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("signup_intents", "pan_name", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("signup_intents", "pan_registered_name", "TEXT NOT NULL DEFAULT ''")
        self._rename_operator_role()
        self._db.execute(
            "INSERT OR IGNORE INTO memberships (user_id, role) SELECT id, role FROM users"
        )
        self._mark_first_super()
        self._ensure_email_role_unique()
        self._purge_orphan_product_accounts()
        self._db.commit()
        try:
            path.chmod(0o600)
        except OSError:
            pass
        self._dummy = hash_password(uuid.uuid4().hex, n=scrypt_n)

    def _ensure_column(self, table: str, column: str, typedef: str) -> None:
        # Identifiers come only from migration callers; still allowlist before PRAGMA/ALTER.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table or ""):
            raise ValueError("invalid table")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column or ""):
            raise ValueError("invalid column")
        if not re.fullmatch(r"[A-Za-z0-9_()'\" ]+", typedef or ""):
            raise ValueError("invalid typedef")
        found = [row[1] for row in self._db.execute(f"PRAGMA table_info({table})")]
        if column not in found:
            self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")

    def _rename_operator_role(self) -> None:
        """The desk role is admin. Rows written as operator become admin."""
        for table in ("users", "memberships", "sessions", "access_tokens", "challenges", "signup_intents"):
            self._db.execute(f"UPDATE {table} SET role = 'admin' WHERE role = 'operator'")
        self._db.commit()

    def _ensure_email_role_unique(self) -> None:
        """One user row per email and role. Customer and retailer may share an inbox."""
        indexed = self._db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_users_email_role'"
        ).fetchone()
        if indexed:
            return
        self._split_multi_role_users()
        create_sql = self._db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if create_sql and create_sql[0] and "email TEXT NOT NULL UNIQUE" in create_sql[0]:
            self._db.executescript(
                """
                CREATE TABLE users_email_role_mig (
                  id TEXT PRIMARY KEY,
                  email TEXT NOT NULL,
                  role TEXT NOT NULL,
                  password_hash TEXT NOT NULL,
                  mfa_secret TEXT,
                  mfa_enabled INTEGER NOT NULL DEFAULT 0,
                  failed_count INTEGER NOT NULL DEFAULT 0,
                  locked_until INTEGER,
                  mfa_last_step INTEGER,
                  created_at INTEGER NOT NULL,
                  sign_in INTEGER NOT NULL DEFAULT 1,
                  is_super INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO users_email_role_mig
                  SELECT id, email, role, password_hash, mfa_secret, mfa_enabled, failed_count,
                         locked_until, mfa_last_step, created_at, sign_in, is_super
                  FROM users;
                DROP TABLE users;
                ALTER TABLE users_email_role_mig RENAME TO users;
                """
            )
        self._db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_role ON users(email, role)")
        self._db.commit()

    def _split_multi_role_users(self) -> None:
        """Move extra memberships onto their own user rows before the email+role key lands."""
        with self._lock:
            rows = self._db.execute(
                """SELECT u.id, u.email, u.role, u.password_hash, u.mfa_secret, u.mfa_enabled,
                          u.failed_count, u.locked_until, u.mfa_last_step, u.created_at,
                          u.sign_in, u.is_super, GROUP_CONCAT(m.role) AS roles
                   FROM users u
                   JOIN memberships m ON m.user_id = u.id
                   GROUP BY u.id
                   HAVING COUNT(m.role) > 1"""
            ).fetchall()
            for row in rows:
                roles = {part for part in (row["roles"] or "").split(",") if part}
                primary = row["role"]
                for role in sorted(roles):
                    if role == primary:
                        continue
                    user_id = str(uuid.uuid4())
                    self._db.execute(
                        """INSERT INTO users
                           (id, email, role, password_hash, mfa_secret, mfa_enabled, failed_count,
                            locked_until, mfa_last_step, created_at, sign_in, is_super)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            user_id,
                            row["email"],
                            role,
                            row["password_hash"],
                            row["mfa_secret"],
                            row["mfa_enabled"],
                            row["failed_count"],
                            row["locked_until"],
                            row["mfa_last_step"],
                            row["created_at"],
                            row["sign_in"],
                            row["is_super"],
                        ),
                    )
                    self._db.execute(
                        "UPDATE memberships SET user_id = ? WHERE user_id = ? AND role = ?",
                        (user_id, row["id"], role),
                    )
                    self._db.execute(
                        "UPDATE account_profiles SET user_id = ? WHERE user_id = ? AND role = ?",
                        (user_id, row["id"], role),
                    )
                    self._db.execute(
                        "UPDATE sessions SET user_id = ? WHERE user_id = ? AND role = ?",
                        (user_id, row["id"], role),
                    )
                    self._db.execute(
                        """UPDATE access_tokens SET user_id = ?
                           WHERE session_id IN (
                             SELECT id FROM sessions WHERE user_id = ? AND role = ?
                           )""",
                        (user_id, user_id, role),
                    )
                    self._db.execute(
                        "UPDATE challenges SET user_id = ? WHERE user_id = ? AND role = ?",
                        (user_id, row["id"], role),
                    )
            if rows:
                self._db.commit()

    def _mark_first_super(self) -> None:
        """The earliest admin is the super admin when none is marked yet."""
        marked = self._db.execute("SELECT 1 FROM users WHERE is_super = 1").fetchone()
        if marked:
            return
        first = self._db.execute(
            """SELECT u.id FROM users u
               JOIN memberships m ON m.user_id = u.id AND m.role = 'admin'
               ORDER BY u.created_at ASC
               LIMIT 1"""
        ).fetchone()
        if not first:
            return
        self._db.execute("UPDATE users SET is_super = 1 WHERE id = ?", (first["id"],))
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def audit(
        self,
        event: str,
        ip: str,
        user_id: str | None = None,
        *,
        request: str = "",
        response: str = "",
    ) -> None:
        from core.actions import scrub_exchange

        req_clean = scrub_exchange(request, mask_codes=True) if request else ""
        resp_clean = scrub_exchange(response, mask_codes=True) if response else ""
        with self._lock:
            self._db.execute(
                "INSERT INTO audit (user_id, event, ip, at, request_text, response_text) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, event, ip, int(time.time()), req_clean, resp_clean),
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
                """SELECT a.id, a.event, a.at, a.request_text, a.response_text, u.email
                   FROM audit a
                   LEFT JOIN users u ON u.id = a.user_id
                   ORDER BY a.id DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "event": row["event"],
                "at": int(row["at"]),
                "email": row["email"] or "",
                "request": row["request_text"] or "",
                "response": row["response_text"] or "",
            }
            for row in rows
        ]

    def remember_service(self, record: dict) -> None:
        """One redacted provider line for the Logs screen. No body and no OTP."""
        with self._lock:
            self._db.execute(
                """INSERT INTO service_log
                   (at, action, app_context, actor, role, target_id, outcome, status,
                    duration_ms, error_code, error_reason, request_text, response_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(time.time()),
                    str(record.get("action") or "")[:80],
                    str(record.get("app_context") or "")[:16],
                    str(record.get("actor") or "")[:320],
                    str(record.get("role") or "")[:16],
                    str(record.get("target_id") or "")[:80],
                    str(record.get("outcome") or "")[:16],
                    int(record.get("status") or 0),
                    max(0, int(record.get("duration_ms") or 0)),
                    str(record.get("error_code") or "")[:40],
                    str(record.get("error_reason") or "")[:200],
                    str(record.get("request") or "")[:1000],
                    str(record.get("response") or "")[:1000],
                ),
            )
            self._db.execute(
                "DELETE FROM service_log WHERE id <= COALESCE((SELECT MAX(id) FROM service_log), 0) - 200"
            )
            self._db.commit()

    def service_logs(self, limit: int = 80) -> list[dict]:
        capped = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._db.execute(
                """SELECT id, at, action, app_context, actor, role, target_id, outcome,
                          status, duration_ms, error_code, error_reason,
                          request_text, response_text
                   FROM service_log
                   ORDER BY id DESC
                   LIMIT ?""",
                (capped,),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "at": int(row["at"]),
                "action": row["action"],
                "app_context": row["app_context"],
                "actor": row["actor"],
                "role": row["role"],
                "target_id": row["target_id"],
                "outcome": row["outcome"],
                "status": int(row["status"]),
                "duration_ms": int(row["duration_ms"]),
                "error_code": row["error_code"],
                "error_reason": row["error_reason"],
                "request": row["request_text"],
                "response": row["response_text"],
            }
            for row in rows
        ]

    def list_people(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT u.id, u.email, u.mfa_enabled, u.sign_in, u.created_at, u.is_super,
                          GROUP_CONCAT(m.role) AS roles
                   FROM users u
                   LEFT JOIN memberships m ON m.user_id = u.id
                   GROUP BY u.id
                   ORDER BY u.email, u.role"""
            ).fetchall()
        people = []
        for row in rows:
            roles = sorted({part for part in (row["roles"] or "").split(",") if part})
            people.append(
                {
                    "id": row["id"],
                    "email": row["email"],
                    "roles": roles,
                    "authenticator": bool(row["mfa_enabled"]),
                    "sign_in": bool(row["sign_in"]),
                    "created_at": int(row["created_at"]),
                    "super": bool(row["is_super"]),
                }
            )
        return people

    def identity_in_use(self, *, pan: str = "", gstin: str = "", udyam: str = "", mobile: str = "") -> str:
        """Which verified document is already on another account. Empty when clear."""
        checks = (
            ("pan", pan),
            ("gstin", gstin),
            ("udyam", udyam),
            ("mobile", mobile),
        )
        with self._lock:
            for kind, value in checks:
                if not value:
                    continue
                if kind not in {"pan", "gstin", "udyam", "mobile"}:
                    continue
                row = self._db.execute(
                    f"SELECT 1 FROM account_profiles WHERE role = 'retailer' AND {kind} = ? LIMIT 1",
                    (value,),
                ).fetchone()
                if row:
                    return kind
        return ""

    def save_outlet(
        self,
        user_id: str,
        role: str,
        *,
        gstin: str,
        udyam: str,
        legal_name: str,
        outlet_name: str,
        shop_lat: str,
        shop_lng: str,
        verification_ip: str,
        location_source: str = "desk",
    ) -> None:
        with self._lock:
            self._db.execute(
                """UPDATE account_profiles
                   SET gstin = ?, udyam = ?, business_legal_name = ?, outlet_name = ?,
                       shop_lat = ?, shop_lng = ?, verification_ip = ?, location_source = ?,
                       business_status = 'pending_review'
                   WHERE user_id = ? AND role = ?""",
                (
                    gstin,
                    udyam,
                    legal_name[:160],
                    outlet_name[:80],
                    shop_lat,
                    shop_lng,
                    verification_ip[:64],
                    location_source[:16],
                    user_id,
                    role,
                ),
            )
            self._db.commit()

    def set_business_status(self, user_id: str, role: str, status: str, note: str = "") -> bool:
        with self._lock:
            cur = self._db.execute(
                """UPDATE account_profiles
                   SET business_status = ?, business_note = ?
                   WHERE user_id = ? AND role = ? AND business_status = 'pending_review'""",
                (status, note[:200], user_id, role),
            )
            self._db.commit()
        return cur.rowcount == 1

    def set_sign_in(self, user_id: str, enabled: bool) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE users SET sign_in = ? WHERE id = ?",
                (1 if enabled else 0, user_id),
            )
            self._db.commit()
        if not enabled:
            self.revoke_user(user_id)

    def _drop_product_user(self, user_id: str, email: str, role: str) -> None:
        """Remove a customer or retailer row that no longer has a membership."""
        with self._lock:
            self._db.execute(
                "DELETE FROM account_profiles WHERE user_id = ? AND role = ?",
                (user_id, role),
            )
            self._db.execute("DELETE FROM backup_codes WHERE user_id = ?", (user_id,))
            self._db.execute(
                "DELETE FROM signup_intents WHERE email = ? AND role = ?",
                (email, role),
            )
            self._db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self._db.commit()
        self.revoke_user(user_id)

    def desk_signup_blocked(self, email: str, role: str) -> bool:
        """True when a live product account exists. Orphan user rows are cleared first."""
        if role not in {"customer", "retailer"}:
            return True
        user = self.user_by_email_role(email, role)
        if user is None:
            return False
        if self.has_membership(user["id"], role):
            return True
        self._drop_product_user(user["id"], user["email"], role)
        return False

    def _purge_orphan_product_accounts(self) -> None:
        """Customer and retailer rows without a membership block desk signup."""
        with self._lock:
            orphans = self._db.execute(
                """SELECT u.id, u.email, u.role FROM users u
                   WHERE u.role IN ('customer', 'retailer')
                     AND NOT EXISTS (
                       SELECT 1 FROM memberships m
                       WHERE m.user_id = u.id AND m.role = u.role
                     )"""
            ).fetchall()
        for row in orphans:
            self._drop_product_user(row["id"], row["email"], row["role"])

    def remove_membership(self, user_id: str, role: str) -> None:
        drop_user = False
        with self._lock:
            user = self._db.execute(
                "SELECT id, email, role FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            self._db.execute(
                "DELETE FROM memberships WHERE user_id = ? AND role = ?",
                (user_id, role),
            )
            self._db.execute(
                "DELETE FROM account_profiles WHERE user_id = ? AND role = ?",
                (user_id, role),
            )
            if user and user["role"] == role and role in {"customer", "retailer"}:
                self._db.execute("DELETE FROM backup_codes WHERE user_id = ?", (user_id,))
                self._db.execute(
                    "DELETE FROM signup_intents WHERE email = ? AND role = ?",
                    (user["email"], role),
                )
                self._db.execute("DELETE FROM users WHERE id = ?", (user_id,))
                drop_user = True
            self._db.commit()
        self.revoke_role_sessions(user_id, role)
        if drop_user:
            self.revoke_user(user_id)

    def revoke_role_sessions(self, user_id: str, role: str) -> None:
        """Drop open sessions that still carry a role the account no longer has."""
        now = int(time.time())
        with self._lock:
            self._db.execute(
                """UPDATE sessions SET revoked_at = ?
                   WHERE user_id = ? AND role = ? AND revoked_at IS NULL""",
                (now, user_id, role),
            )
            self._db.execute(
                """UPDATE access_tokens SET revoked_at = ?
                   WHERE user_id = ? AND role = ? AND revoked_at IS NULL""",
                (now, user_id, role),
            )
            self._db.commit()

    def set_password_hash(self, user_id: str, digest: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (digest, user_id),
            )
            self._db.commit()

    def clear_mfa(self, user_id: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE users SET mfa_secret = NULL, mfa_enabled = 0, mfa_last_step = NULL WHERE id = ?",
                (user_id,),
            )
            self._db.execute("DELETE FROM backup_codes WHERE user_id = ?", (user_id,))
            self._db.commit()

    def open_sessions(self, user_id: str) -> list[dict]:
        """One live tip per login family (device). Rotated tips are revoked and omitted."""
        now = int(time.time())
        with self._lock:
            rows = self._db.execute(
                """SELECT id, role, scope, expires_at, created_at, family_id,
                          device_key, user_agent, ip
                   FROM sessions
                   WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?
                   ORDER BY created_at DESC""",
                (user_id, now),
            ).fetchall()
        out = []
        for row in rows:
            ua = (row["user_agent"] if "user_agent" in row.keys() else "") or ""
            device = (row["device_key"] if "device_key" in row.keys() else "") or ""
            out.append(
                {
                    "id": row["id"],
                    "role": row["role"] or "",
                    "scope": row["scope"],
                    "expires_at": int(row["expires_at"]),
                    "created_at": int(row["created_at"]),
                    "family_id": row["family_id"],
                    "device_bound": bool(device),
                    "device_label": self._device_label(ua, device),
                    "ip": (row["ip"] if "ip" in row.keys() else "") or "",
                }
            )
        return out

    @staticmethod
    def _device_label(user_agent: str, device_key: str) -> str:
        ua = (user_agent or "").strip()
        if not ua:
            return "Unknown device" + (f" · {device_key[:8]}" if device_key else "")
        lower = ua.lower()
        browser = "Browser"
        if "edg/" in lower:
            browser = "Edge"
        elif "chrome/" in lower and "chromium" not in lower:
            browser = "Chrome"
        elif "firefox/" in lower:
            browser = "Firefox"
        elif "safari/" in lower and "chrome/" not in lower:
            browser = "Safari"
        system = "device"
        if "android" in lower:
            system = "Android"
        elif "iphone" in lower or "ipad" in lower:
            system = "iOS"
        elif "mac os" in lower or "macintosh" in lower:
            system = "macOS"
        elif "windows" in lower:
            system = "Windows"
        elif "linux" in lower:
            system = "Linux"
        return f"{browser} on {system}"

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
            self._drop_expired_signups()
            rows = self._db.execute(
                """SELECT id, email, mobile, role, email_ok, mobile_ok, aadhaar_ok, pan_ok,
                          aadhaar_ref, expires_at, created_at
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
                    "id": row["id"],
                    "email": row["email"],
                    "mobile_last4": digits[-4:] if len(digits) >= 4 else "",
                    "role": row["role"],
                    "email_ok": bool(row["email_ok"]),
                    "mobile_ok": bool(row["mobile_ok"]),
                    "aadhaar_ok": bool(row["aadhaar_ok"]),
                    "aadhaar_pending": bool(row["aadhaar_ref"]) and not bool(row["aadhaar_ok"]),
                    "pan_ok": bool(row["pan_ok"]),
                    "open": True,
                    "created_at": int(row["created_at"]),
                }
            )
        return listed

    def recent_verified_accounts(self, limit: int = 40) -> list[dict]:
        """Verified customers and retailers. Each user row is one email+role account."""
        capped = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._db.execute(
                """SELECT u.id AS user_id, u.email, u.role, u.created_at AS user_created,
                          p.mobile_last4, p.email_ok, p.mobile_ok, p.aadhaar_ok, p.pan_ok,
                          p.pan_mask, p.digilocker_ref, p.pan_name_hint,
                          p.business_status, p.business_legal_name, p.shop_lat, p.shop_lng,
                          u.sign_in, p.created_at AS profile_created
                   FROM users u
                   LEFT JOIN account_profiles p
                     ON p.user_id = u.id AND p.role = u.role
                   WHERE u.role IN ('customer', 'retailer')
                   ORDER BY COALESCE(p.created_at, u.created_at) DESC
                   LIMIT ?""",
                (capped,),
            ).fetchall()
        listed = []
        for row in rows:
            has_profile = row["profile_created"] is not None
            if has_profile:
                email_ok = bool(row["email_ok"])
                mobile_ok = bool(row["mobile_ok"])
                aadhaar_ok = bool(row["aadhaar_ok"])
                pan_ok = bool(row["pan_ok"])
            else:
                email_ok = mobile_ok = True
                aadhaar_ok = pan_ok = row["role"] == "customer"
            listed.append(
                {
                    "user_id": row["user_id"],
                    "email": row["email"],
                    "role": row["role"],
                    "mobile_last4": (row["mobile_last4"] or "") if has_profile else "",
                    "email_ok": email_ok,
                    "mobile_ok": mobile_ok,
                    "aadhaar_ok": aadhaar_ok,
                    "pan_ok": pan_ok,
                    "pan_mask": (row["pan_mask"] or "") if has_profile else "",
                    "digilocker_ref": (row["digilocker_ref"] or "") if has_profile else "",
                    "pan_name_hint": (row["pan_name_hint"] or "") if has_profile else "",
                    "business_status": (row["business_status"] or "") if has_profile else "",
                    "business_legal_name": (row["business_legal_name"] or "") if has_profile else "",
                    "shop_lat": (row["shop_lat"] or "") if has_profile else "",
                    "shop_lng": (row["shop_lng"] or "") if has_profile else "",
                    "sign_in": bool(row["sign_in"]),
                    "verified_at": int(row["profile_created"] or row["user_created"]),
                }
            )
        return listed

    def ip_blocked(self, ip: str) -> bool:
        # Loopback is every local app. The per-account lock still applies.
        if ip in {"127.0.0.1", "::1"}:
            return False
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

    def roles_for(self, user_id: str) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT role FROM memberships WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return sorted(row["role"] for row in rows)

    def save_profile(
        self,
        user_id: str,
        role: str,
        mobile: str,
        email_ok: bool,
        mobile_ok: bool,
        aadhaar_ok: bool,
        pan_ok: bool,
        pan_mask: str = "",
        digilocker_ref: str = "",
        pan_name_hint: str = "",
        pan: str = "",
        pan_name: str = "",
        pan_registered_name: str = "",
        digilocker_verification_id: str = "",
    ) -> None:
        """Desk onboarding record. Masked fields stay for verification lists; full values for KYC file."""
        digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
        last4 = digits[-4:] if len(digits) >= 4 else ""
        mobile_store = digits if len(digits) >= 10 else ""
        pan_store = (pan or "").strip().upper()
        with self._lock:
            self._db.execute(
                """INSERT INTO account_profiles
                   (user_id, role, mobile_last4, email_ok, mobile_ok, aadhaar_ok, pan_ok,
                    pan_mask, digilocker_ref, pan_name_hint, mobile, pan, pan_name,
                    pan_registered_name, digilocker_verification_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, role) DO UPDATE SET
                     mobile_last4 = excluded.mobile_last4,
                     email_ok = excluded.email_ok,
                     mobile_ok = excluded.mobile_ok,
                     aadhaar_ok = excluded.aadhaar_ok,
                     pan_ok = excluded.pan_ok,
                     pan_mask = CASE WHEN excluded.pan_mask != '' THEN excluded.pan_mask ELSE pan_mask END,
                     digilocker_ref = CASE WHEN excluded.digilocker_ref != '' THEN excluded.digilocker_ref ELSE digilocker_ref END,
                     pan_name_hint = CASE WHEN excluded.pan_name_hint != '' THEN excluded.pan_name_hint ELSE pan_name_hint END,
                     mobile = CASE WHEN excluded.mobile != '' THEN excluded.mobile ELSE mobile END,
                     pan = CASE WHEN excluded.pan != '' THEN excluded.pan ELSE pan END,
                     pan_name = CASE WHEN excluded.pan_name != '' THEN excluded.pan_name ELSE pan_name END,
                     pan_registered_name = CASE WHEN excluded.pan_registered_name != ''
                       THEN excluded.pan_registered_name ELSE pan_registered_name END,
                     digilocker_verification_id = CASE WHEN excluded.digilocker_verification_id != ''
                       THEN excluded.digilocker_verification_id ELSE digilocker_verification_id END""",
                (
                    user_id,
                    role,
                    last4,
                    1 if email_ok else 0,
                    1 if mobile_ok else 0,
                    1 if aadhaar_ok else 0,
                    1 if pan_ok else 0,
                    pan_mask or "",
                    digilocker_ref or "",
                    pan_name_hint or "",
                    mobile_store,
                    pan_store,
                    (pan_name or "").strip(),
                    (pan_registered_name or "").strip(),
                    (digilocker_verification_id or "").strip(),
                    int(time.time()),
                ),
            )
            self._db.commit()

    def patch_profile_verification(
        self,
        user_id: str,
        role: str,
        pan_mask: str = "",
        digilocker_ref: str = "",
        pan_name_hint: str = "",
        *,
        mobile: str = "",
        pan: str = "",
        pan_name: str = "",
        pan_registered_name: str = "",
        digilocker_verification_id: str = "",
    ) -> bool:
        """Backfill verification on legacy accounts or correction after onboarding."""
        digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
        mobile_store = digits if len(digits) >= 10 else ""
        pan_store = (pan or "").strip().upper()
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM account_profiles WHERE user_id = ? AND role = ?",
                (user_id, role),
            ).fetchone()
            if not row:
                return False
            self._db.execute(
                """UPDATE account_profiles SET
                     pan_mask = CASE WHEN ? != '' THEN ? ELSE pan_mask END,
                     digilocker_ref = CASE WHEN ? != '' THEN ? ELSE digilocker_ref END,
                     pan_name_hint = CASE WHEN ? != '' THEN ? ELSE pan_name_hint END,
                     mobile = CASE WHEN ? != '' THEN ? ELSE mobile END,
                     mobile_last4 = CASE WHEN ? != '' THEN substr(?, -4) ELSE mobile_last4 END,
                     pan = CASE WHEN ? != '' THEN ? ELSE pan END,
                     pan_name = CASE WHEN ? != '' THEN ? ELSE pan_name END,
                     pan_registered_name = CASE WHEN ? != '' THEN ? ELSE pan_registered_name END,
                     digilocker_verification_id = CASE WHEN ? != '' THEN ? ELSE digilocker_verification_id END
                   WHERE user_id = ? AND role = ?""",
                (
                    pan_mask,
                    pan_mask,
                    digilocker_ref,
                    digilocker_ref,
                    pan_name_hint,
                    pan_name_hint,
                    mobile_store,
                    mobile_store,
                    mobile_store,
                    mobile_store,
                    pan_store,
                    pan_store,
                    (pan_name or "").strip(),
                    (pan_name or "").strip(),
                    (pan_registered_name or "").strip(),
                    (pan_registered_name or "").strip(),
                    (digilocker_verification_id or "").strip(),
                    (digilocker_verification_id or "").strip(),
                    user_id,
                    role,
                ),
            )
            self._db.commit()
        return True

    def profiles_for(self, user_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT role, mobile_last4, email_ok, mobile_ok, aadhaar_ok, pan_ok,
                          pan_mask, digilocker_ref, pan_name_hint, mobile, pan, pan_name,
                          pan_registered_name, digilocker_verification_id,
                          display_name, outlet_name, city, address, gstin, udyam,
                          business_legal_name, business_status, shop_lat, shop_lng, location_source,
                          verification_ip, business_note, created_at
                   FROM account_profiles WHERE user_id = ? ORDER BY role""",
                (user_id,),
            ).fetchall()
        return [
            {
                "role": row["role"],
                "mobile_last4": row["mobile_last4"] or "",
                "mobile": row["mobile"] or "",
                "email_ok": bool(row["email_ok"]),
                "mobile_ok": bool(row["mobile_ok"]),
                "aadhaar_ok": bool(row["aadhaar_ok"]),
                "pan_ok": bool(row["pan_ok"]),
                "pan_mask": row["pan_mask"] or "",
                "pan": row["pan"] or "",
                "pan_name": row["pan_name"] or "",
                "pan_registered_name": row["pan_registered_name"] or "",
                "digilocker_ref": row["digilocker_ref"] or "",
                "digilocker_verification_id": row["digilocker_verification_id"] or "",
                "pan_name_hint": row["pan_name_hint"] or "",
                "display_name": row["display_name"] or "",
                "outlet_name": row["outlet_name"] or "",
                "city": row["city"] or "",
                "address": row["address"] or "",
                "gstin": row["gstin"] or "",
                "udyam": row["udyam"] or "",
                "business_legal_name": row["business_legal_name"] or "",
                "business_status": row["business_status"] or "",
                "shop_lat": row["shop_lat"] or "",
                "shop_lng": row["shop_lng"] or "",
                "location_source": row["location_source"] or "",
                "verification_ip": row["verification_ip"] or "",
                "business_note": row["business_note"] or "",
                "recorded_at": int(row["created_at"]),
            }
            for row in rows
        ]

    def self_profile(self, user_id: str, role: str) -> dict:
        with self._lock:
            user = self._db.execute(
                "SELECT id, email, role, mfa_enabled, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            prof = self._db.execute(
                """SELECT mobile_last4, email_ok, mobile_ok, aadhaar_ok, pan_ok,
                          pan_mask, pan_name_hint, digilocker_ref,
                          display_name, outlet_name, city, address, gstin, created_at
                   FROM account_profiles WHERE user_id = ? AND role = ?""",
                (user_id, role),
            ).fetchone()
        checks = {
            "email_ok": bool(prof["email_ok"]) if prof else False,
            "mobile_ok": bool(prof["mobile_ok"]) if prof else False,
            "aadhaar_ok": bool(prof["aadhaar_ok"]) if prof else False,
            "pan_ok": bool(prof["pan_ok"]) if prof else False,
        }
        kyc_verified = (
            checks["email_ok"] and checks["mobile_ok"] and checks["aadhaar_ok"] and checks["pan_ok"]
            if role == "retailer"
            else checks["email_ok"] and checks["mobile_ok"]
        )
        prefix = "RET" if role == "retailer" else ("ADM" if role == "admin" else "CUS")
        short_id = (user_id or "").replace("-", "").upper()[:8]
        return {
            "email": user["email"] if user else "",
            "role": role,
            "account_id": f"{prefix}-{short_id}" if short_id else "",
            "mfa_enabled": bool(user["mfa_enabled"]) if user else False,
            "created_at": int(user["created_at"]) if user else 0,
            "kyc_verified": kyc_verified,
            "checks": checks,
            "mobile_last4": prof["mobile_last4"] if prof else "",
            "pan_mask": prof["pan_mask"] if prof else "",
            "pan_name_hint": prof["pan_name_hint"] if prof else "",
            "digilocker_ref": prof["digilocker_ref"] if prof else "",
            "display_name": (prof["display_name"] if prof else "") or (prof["pan_name_hint"] if prof else ""),
            "outlet_name": prof["outlet_name"] if prof else "",
            "city": prof["city"] if prof else "",
            "address": prof["address"] if prof else "",
            "gstin": prof["gstin"] if prof else "",
        }

    def update_self_profile(
        self,
        user_id: str,
        role: str,
        *,
        display_name: str = "",
        outlet_name: str = "",
        city: str = "",
        address: str = "",
        gstin: str = "",
    ) -> dict:
        now = int(time.time())
        with self._lock:
            self._db.execute(
                """INSERT INTO account_profiles
                   (user_id, role, display_name, outlet_name, city, address, gstin, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, role) DO UPDATE SET
                     display_name = excluded.display_name,
                     outlet_name = excluded.outlet_name,
                     city = excluded.city,
                     address = excluded.address,
                     gstin = CASE
                       WHEN business_status IN ('pending_review', 'approved') AND gstin != '' THEN gstin
                       ELSE excluded.gstin
                     END,
                     outlet_name = CASE
                       WHEN business_status IN ('pending_review', 'approved') AND outlet_name != '' THEN outlet_name
                       ELSE excluded.outlet_name
                     END""",
                (
                    user_id,
                    role,
                    display_name[:80],
                    outlet_name[:80],
                    city[:64],
                    address[:200],
                    gstin[:20],
                    now,
                ),
            )
            self._db.commit()
        return self.self_profile(user_id, role)

    def revoke_other_sessions(self, user_id: str, keep_session_id: str) -> int:
        now = int(time.time())
        with self._lock:
            cur = self._db.execute(
                """UPDATE sessions SET revoked_at = ?
                   WHERE user_id = ? AND id != ? AND revoked_at IS NULL""",
                (now, user_id, keep_session_id),
            )
            self._db.execute(
                """UPDATE access_tokens SET revoked_at = ?
                   WHERE user_id = ? AND session_id != ? AND revoked_at IS NULL""",
                (now, user_id, keep_session_id),
            )
            self._db.commit()
            return cur.rowcount or 0

    def add_membership(self, user_id: str, role: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO memberships (user_id, role) VALUES (?, ?)",
                (user_id, role),
            )
            self._db.commit()

    def user_by_email(self, email: str) -> sqlite3.Row | None:
        """Return the row only when that email has one account."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM users WHERE email = ? ORDER BY created_at",
                (email,),
            ).fetchall()
        if len(rows) == 1:
            return rows[0]
        return None

    def user_by_email_role(self, email: str, role: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(
                "SELECT * FROM users WHERE email = ? AND role = ?",
                (email, role),
            ).fetchone()

    def admin_with_email(self, email: str) -> sqlite3.Row | None:
        return self.user_by_email_role(email, "admin")

    def user_by_id(self, user_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def create_user(self, email: str, password: str, role: str, *, close_admin_signup: bool = False) -> bool:
        """Return False when the email already exists. Always spends a password hash.

        Public register passes close_admin_signup so a second admin cannot win
        the first-admin race. The desk add-admin path leaves it false.
        """
        digest = hash_password(password, n=self.scrypt_n)
        with self._lock:
            exists = self._db.execute(
                "SELECT 1 FROM users WHERE email = ? AND role = ?", (email, role)
            ).fetchone()
            if exists:
                return False
            if close_admin_signup and role == "admin" and self._db.execute(
                "SELECT 1 FROM memberships WHERE role = 'admin' LIMIT 1"
            ).fetchone():
                return False
            try:
                user_id = str(uuid.uuid4())
                is_super = 0
                if role == "admin" and not self._db.execute("SELECT 1 FROM users WHERE is_super = 1").fetchone():
                    is_super = 1
                self._db.execute(
                    """INSERT INTO users
                       (id, email, role, password_hash, created_at, is_super)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, email, role, digest, int(time.time()), is_super),
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
        """Insert a verified account. False when that email already has this role."""
        with self._lock:
            exists = self._db.execute(
                "SELECT 1 FROM users WHERE email = ? AND role = ?", (email, role)
            ).fetchone()
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

    def signup_any(self, signup_id: str) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(
                "SELECT * FROM signup_intents WHERE id = ?",
                (signup_id,),
            ).fetchone()

    def signup(self, signup_id: str) -> sqlite3.Row | None:
        with self._lock:
            self._drop_expired_signups()
            return self._db.execute(
                "SELECT * FROM signup_intents WHERE id = ?",
                (signup_id,),
            ).fetchone()

    def mark_signup(self, signup_id: str, **fields) -> None:
        if not fields:
            return
        allowed = {
            "email_ok",
            "mobile_ok",
            "aadhaar_ok",
            "pan_ok",
            "aadhaar_ref",
            "pan_mask",
            "pan_name_hint",
            "pan",
            "pan_name",
            "pan_registered_name",
            "email_code_hash",
            "sms_code_hash",
            "expires_at",
        }
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

    def note_signup_failure(self, signup_id: str) -> int:
        with self._lock:
            self._db.execute(
                "UPDATE signup_intents SET fails = COALESCE(fails, 0) + 1 WHERE id = ?",
                (signup_id,),
            )
            row = self._db.execute(
                "SELECT fails FROM signup_intents WHERE id = ?",
                (signup_id,),
            ).fetchone()
            self._db.commit()
        return int(row["fails"]) if row else 0

    def _drop_expired_signups(self) -> None:
        """Caller holds self._lock. Drop unfinished signups, including any PAN on them."""
        from auth.verify import SIGNUP_INTENT_TTL

        now = int(time.time())
        cutoff = now - SIGNUP_INTENT_TTL
        self._db.execute(
            "DELETE FROM signup_intents WHERE expires_at < ? OR created_at < ?",
            (now, cutoff),
        )
        self._db.commit()

    def delete_signup(self, signup_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM signup_intents WHERE id = ?", (signup_id,))
            self._db.commit()

    def check_password(self, user: sqlite3.Row | None, password: str) -> bool:
        stored = user["password_hash"] if user else self._dummy
        return verify_password(password, stored) and user is not None

    def register_failure(self, user: sqlite3.Row) -> int:
        now = int(time.time())
        with self._lock:
            row = self._db.execute(
                "SELECT failed_count FROM users WHERE id = ?",
                (user["id"],),
            ).fetchone()
            count = int(row["failed_count"]) + 1 if row else 1
            locked = now + LOCK_SECONDS if count >= MAX_FAILS else None
            self._db.execute(
                "UPDATE users SET failed_count = ?, locked_until = ? WHERE id = ?",
                (count, locked, user["id"]),
            )
            self._db.commit()
        return count

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

    def save_session(
        self,
        user_id: str,
        refresh: str,
        scope: str,
        expires_at: int,
        family_id: str | None = None,
        role: str = "",
        device_key: str = "",
        user_agent: str = "",
        ip: str = "",
        *,
        continue_device: bool = True,
    ) -> str:
        """Mint a session tip. Same user+role+device_key reuses the login family (no duplicate device rows)."""
        session_id = str(uuid.uuid4())
        device = (device_key or "").strip()[:128]
        ua = (user_agent or "").strip()[:300]
        addr = (ip or "").strip()[:64]
        now = int(time.time())
        with self._lock:
            family = family_id
            if continue_device and device and scope == "full":
                tip = self._db.execute(
                    """SELECT id, family_id FROM sessions
                       WHERE user_id = ? AND IFNULL(role, '') = ? AND device_key = ?
                         AND scope = ? AND revoked_at IS NULL AND expires_at > ?
                       ORDER BY created_at DESC LIMIT 1""",
                    (user_id, role or "", device, scope, now),
                ).fetchone()
                if tip:
                    family = tip["family_id"]
                    self._db.execute(
                        "UPDATE sessions SET revoked_at = ?, replaced_by = ? WHERE id = ?",
                        (now, session_id, tip["id"]),
                    )
                    self._db.execute(
                        """UPDATE access_tokens SET revoked_at = ?
                           WHERE session_id = ? AND revoked_at IS NULL""",
                        (now, tip["id"]),
                    )
            if not family:
                family = str(uuid.uuid4())
            self._db.execute(
                """INSERT INTO sessions
                   (id, user_id, refresh_hash, family_id, scope, expires_at, created_at, role,
                    device_key, user_agent, ip)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    user_id,
                    token_hash(refresh),
                    family,
                    scope,
                    expires_at,
                    now,
                    role,
                    device,
                    ua,
                    addr,
                ),
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
                   (id, user_id, refresh_hash, family_id, scope, expires_at, created_at, role,
                    device_key, user_agent, ip)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    row["user_id"],
                    token_hash(new_refresh),
                    row["family_id"],
                    row["scope"],
                    expires_at,
                    now,
                    row["role"] if "role" in row.keys() else "",
                    row["device_key"] if "device_key" in row.keys() else "",
                    row["user_agent"] if "user_agent" in row.keys() else "",
                    row["ip"] if "ip" in row.keys() else "",
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

    def save_challenge(
        self, token: str, user_id: str, expires_at: int, role: str = "", device_key: str = ""
    ) -> None:
        with self._lock:
            self._db.execute(
                """INSERT INTO challenges (token_hash, user_id, expires_at, role, device_key)
                   VALUES (?, ?, ?, ?, ?)""",
                (token_hash(token), user_id, expires_at, role, (device_key or "").strip()[:128]),
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
                "UPDATE users SET mfa_secret = ?, mfa_enabled = 0, mfa_last_step = NULL WHERE id = ?",
                (secret, user_id),
            )
            self._db.execute("DELETE FROM backup_codes WHERE user_id = ?", (user_id,))
            self._db.executemany(
                "INSERT INTO backup_codes (code_hash, user_id) VALUES (?, ?)",
                [(hash_backup(code), user_id) for code in codes],
            )
            self._db.commit()
        return codes

    def claim_totp_step(self, user_id: str, step: int) -> bool:
        """Accept a counter once. A reused step does not open another session."""
        with self._lock:
            row = self._db.execute(
                "SELECT mfa_last_step FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                return False
            last = row["mfa_last_step"]
            if last is not None and int(last) >= int(step):
                return False
            self._db.execute(
                "UPDATE users SET mfa_last_step = ? WHERE id = ?",
                (int(step), user_id),
            )
            self._db.commit()
        return True

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
