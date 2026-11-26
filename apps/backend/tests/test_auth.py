import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from http.server import ThreadingHTTPServer

from auth.security import totp_code


def _next_totp(secret: str) -> str:
    """The following 30-second step. Confirm already claimed the current one."""
    step = int(time.time()) // 30 + 1
    return totp_code(secret, step * 30 + 1)
from auth.server import AuthApp, build_handler
from auth.verify import LiveVerify, load_mail_env
from core.actions import bind_action, redact, reset_action
from integrations import kaleyra
from integrations.kaleyra import load_local_env, send_otp


class FakeVerify:
    def __init__(self):
        self.email_code = ""
        self.sms_code = ""
        self.fail_link = False
        self.last_id = ""
        self.digilocker_ready = True

    def send_email(self, to, code, role=None):
        self.email_code = code
        return True

    def send_sms(self, mobile, code, role=None):
        self.sms_code = code
        return True

    def digilocker_link(self, verification_id):
        if self.fail_link:
            return None
        self.last_id = verification_id
        return "https://verification.example/dgl/test"

    def digilocker_ok(self, verification_id):
        return verification_id == self.last_id and not self.fail_link

    def digilocker_poll(self, verification_id):
        if self.fail_link:
            return "rejected"
        if verification_id == self.last_id and self.digilocker_ready:
            return "authenticated"
        if verification_id == self.last_id:
            return "pending"
        return "pending"

    def pan_verify(self, pan, name):
        ok = pan == "ABCDE1234F" and len(name) >= 2
        registered = "ParkPe User" if ok else ""
        return ok, registered

    def pan_check(self, pan, name):
        ok, _registered = self.pan_verify(pan, name)
        return ok


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.verify = FakeVerify()
        self.app = AuthApp(
            data_dir=Path(self.tmp.name),
            origins={"http://127.0.0.1:4500"},
            scrypt_n=2**12,
            cookie_secure=False,
            samesite="Lax",
            verifiers=self.verify,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.app.origins.add(self.base)
        self.cookies = {}
        self.operator_secret = ""

    def tearDown(self):
        self.server.shutdown()
        self.app.close()
        self.tmp.cleanup()

    def request(self, method, path, payload=None, origin="http://127.0.0.1:4500", header=True):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        if header:
            req.add_header("X-Auth-Request", "1")
        if origin:
            req.add_header("Origin", origin)
        if self.cookies:
            req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
        try:
            with urllib.request.urlopen(req) as res:
                self._store_cookies(res.headers.get_all("Set-Cookie") or [])
                raw = res.read()
                return res.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            self._store_cookies(err.headers.get_all("Set-Cookie") or [])
            raw = err.read()
            return err.code, json.loads(raw) if raw else {}

    def _store_cookies(self, values):
        for value in values:
            pair = value.split(";", 1)[0]
            name, cookie = pair.split("=", 1)
            if cookie == "":
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = cookie

    def operator_session(self):
        self.cookies = {}
        self.request(
            "POST",
            "/api/auth/register",
            {"email": "ops@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        status, body = self.request(
            "POST",
            "/api/auth/login",
            {"email": "ops@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(status, 200, body)
        if body.get("mfa_setup_required"):
            _, setup = self.request("POST", "/api/auth/mfa/setup", {}, origin=self.base)
            self.operator_secret = setup["secret"]
            confirmed, _ = self.request(
                "POST",
                "/api/auth/mfa/confirm",
                {"code": totp_code(setup["secret"])},
                origin=self.base,
            )
            self.assertEqual(confirmed, 200)
        elif body.get("mfa_required"):
            confirmed, _ = self.request(
                "POST",
                "/api/auth/mfa",
                {"code": _next_totp(self.operator_secret)},
                origin=self.base,
            )
            self.assertEqual(confirmed, 200)

    def account(self, email, role, mobile="9800000010", password="Counter-outlet-1042"):
        me_status, me = self.request("GET", "/api/auth/me", origin=self.base)
        if me_status != 200 or me.get("role") != "admin":
            self.operator_session()
        status, started = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": email, "mobile": mobile, "password": password, "role": role},
            origin=self.base,
        )
        self.assertEqual(status, 200, started)
        status, contact = self.request(
            "POST",
            "/api/auth/signup/contact",
            {
                "signup_id": started["signup_id"],
                "email_code": self.verify.email_code,
                "sms_code": self.verify.sms_code,
            },
            origin=self.base,
        )
        self.assertEqual(status, 200, contact)
        if role == "customer":
            self.assertTrue(contact["account_ready"])
            self.cookies = {}
            return
        status, sent = self.request(
            "POST",
            "/api/auth/signup/aadhaar",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(status, 200, sent)
        self.assertIn("url", sent)
        status, confirmed = self.request(
            "POST",
            "/api/auth/signup/aadhaar/confirm",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(status, 200, confirmed)
        status, pan = self.request(
            "POST",
            "/api/auth/signup/pan",
            {"signup_id": started["signup_id"], "pan": "ABCDE1234F", "name": "ParkPe User"},
            origin=self.base,
        )
        self.assertEqual(status, 200, pan)
        self.assertTrue(pan["account_ready"])
        self.cookies = {}

    def test_login_hides_whether_the_email_exists(self):
        missing = self.request("POST", "/api/auth/login", {"email": "no@outlet.test", "password": "not-a-real-pass", "role": "retailer"})
        self.account("owner@outlet.test", "retailer")
        wrong = self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "not-a-real-pass", "role": "retailer"})
        self.assertEqual(missing, wrong)
        self.assertNotIn("auth_access", self.cookies)

    def test_customer_password_does_not_open_the_retailer_counter(self):
        self.account("buyer@shop.test", "customer", "9800000011")
        status, body = self.request("POST", "/api/auth/login", {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "retailer"})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "Email or password is incorrect.")

    def test_counter_stays_closed_until_authenticator_is_on(self):
        self.account("owner@outlet.test", "retailer")
        status, body = self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        self.assertEqual(status, 200)
        self.assertTrue(body["mfa_setup_required"])
        me, me_body = self.request("GET", "/api/auth/me")
        self.assertEqual(me, 403)
        self.assertTrue(me_body["mfa_setup_required"])
        _, setup = self.request("POST", "/api/auth/mfa/setup", {})
        code = totp_code(setup["secret"])
        ok, session = self.request("POST", "/api/auth/mfa/confirm", {"code": code})
        self.assertEqual(ok, 200)
        self.assertEqual(session["email"], "owner@outlet.test")
        self.cookies = {}
        status, challenge = self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        self.assertTrue(challenge["mfa_required"])
        self.assertNotIn("auth_access", self.cookies)
        denied, _ = self.request("GET", "/api/auth/me")
        self.assertEqual(denied, 401)
        passed, user = self.request("POST", "/api/auth/mfa", {"code": _next_totp(setup["secret"])})
        self.assertEqual(passed, 200)
        self.assertEqual(user["role"], "retailer")

    def test_wrong_code_does_not_open_a_session(self):
        self._enrolled()
        self.cookies = {}
        self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        status, _ = self.request("POST", "/api/auth/mfa", {"code": "000000"})
        self.assertEqual(status, 401)
        self.assertNotIn("auth_access", self.cookies)

    def test_failed_logins_lock_the_account(self):
        self.account("owner@outlet.test", "retailer")
        for _ in range(5):
            self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "wrong-password-1", "role": "retailer"})
        status, body = self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "Email or password is incorrect.")

    def test_logout_and_refresh_reuse_kill_the_session(self):
        secret = self._enrolled()
        self.assertEqual(self.request("GET", "/api/auth/me")[0], 200)
        first_refresh = self.cookies["auth_refresh"]
        self.request("POST", "/api/auth/refresh", {})
        self.assertNotEqual(self.cookies["auth_refresh"], first_refresh)
        self.cookies["auth_refresh"] = first_refresh
        status, _ = self.request("POST", "/api/auth/refresh", {})
        self.assertEqual(status, 401)
        self.assertNotIn("auth_access", self.cookies)
        self.cookies = {}
        self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        self.request("POST", "/api/auth/mfa", {"code": _next_totp(secret)})
        self.request("POST", "/api/auth/logout", {})
        self.assertEqual(self.request("GET", "/api/auth/me")[0], 401)

    def test_other_origins_and_plain_browser_posts_are_blocked(self):
        status, _ = self.request("POST", "/api/auth/login", {"email": "a@b.co", "password": "Counter-outlet-1042", "role": "retailer"}, origin="http://evil.test")
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/api/auth/me", header=False)
        self.assertEqual(status, 403)

    def test_console_page_and_single_operator(self):
        request = urllib.request.Request(self.base + "/")
        with urllib.request.urlopen(request) as response:
            page = response.read().decode()
            self.assertEqual(response.status, 200)
            self.assertIn("Backend", page)
            self.assertIn("/console.js", page)
            self.assertIn("Recent auth", page)
            self.assertIn("Add account", page)
            self.assertIn("Account created", page)
            self.assertIn("Users", page)
            self.assertIn("Verification", page)
            self.assertIn("Logs", page)
            self.assertIn("User actions", page)
            self.assertIn("API logs", page)
            self.assertIn("Copy this log", page)
            self.assertIn("Processes", page)
        status, body = self.request("GET", "/api/auth/setup")
        self.assertEqual(status, 200)
        self.assertTrue(body["signup_open"])
        created, _ = self.request(
            "POST",
            "/api/auth/register",
            {"email": "ops@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
        )
        self.assertEqual(created, 200)
        closed, message = self.request(
            "POST",
            "/api/auth/register",
            {"email": "second@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
        )
        self.assertEqual(closed, 403)
        self.assertEqual(message["error"], "Admin signup is closed.")
        self.account("shop@hub.test", "retailer", "9800000012")
        denied, body = self.request(
            "POST",
            "/api/auth/login",
            {"email": "shop@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
        )
        self.assertEqual(denied, 401)
        self.assertEqual(body["error"], "Email or password is incorrect.")

    def test_short_password_is_rejected(self):
        closed, closed_body = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": "owner@outlet.test", "mobile": "9800000010", "password": "short", "role": "retailer"},
        )
        self.assertEqual(closed, 403)
        self.assertEqual(closed_body["error"], "An admin creates this account.")
        self.operator_session()
        status, body = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": "owner@outlet.test", "mobile": "9800000010", "password": "short", "role": "retailer"},
            origin=self.base,
        )
        self.assertEqual(status, 400)
        self.assertIn("12", body["error"])
        still_closed, _ = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": "owner@outlet.test", "mobile": "9800000010", "password": "Counter-outlet-1042", "role": "retailer"},
        )
        self.assertEqual(still_closed, 403)

    def test_unverified_register_does_not_open_an_account(self):
        status, body = self.request(
            "POST",
            "/api/auth/register",
            {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"},
        )
        self.assertEqual(status, 400)
        self.assertIn("Verify", body["error"])
        denied, _ = self.request(
            "POST",
            "/api/auth/login",
            {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"},
        )
        self.assertEqual(denied, 401)

    def test_verified_accounts_appear_on_the_desk_list(self):
        self.account("verified@shop.test", "customer", "9800000082")
        self.operator_session()
        listed, body = self.request("GET", "/api/auth/desk/signups", origin=self.base)
        self.assertEqual(listed, 200)
        emails = [row["email"] for row in body["verified"]]
        self.assertIn("verified@shop.test", emails)

    def test_aadhaar_status_polls_cashfree_before_pan(self):
        self.verify.digilocker_ready = False
        self.operator_session()
        status, started = self.request(
            "POST",
            "/api/auth/signup/start",
            {
                "email": "poll@outlet.test",
                "mobile": "9800000081",
                "password": "Counter-outlet-1042",
                "role": "retailer",
            },
            origin=self.base,
        )
        self.assertEqual(status, 200, started)
        self.request(
            "POST",
            "/api/auth/signup/contact",
            {
                "signup_id": started["signup_id"],
                "email_code": self.verify.email_code,
                "sms_code": self.verify.sms_code,
            },
            origin=self.base,
        )
        self.request("POST", "/api/auth/signup/aadhaar", {"signup_id": started["signup_id"]}, origin=self.base)
        pending, body = self.request(
            "POST",
            "/api/auth/signup/aadhaar/status",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(pending, 200)
        self.assertEqual(body["state"], "pending")
        self.verify.digilocker_ready = True
        done, body2 = self.request(
            "POST",
            "/api/auth/signup/aadhaar/status",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(done, 200)
        self.assertTrue(body2["authenticated"])
        self.assertEqual(body2["state"], "authenticated")

    def test_failed_aadhaar_does_not_create_the_retailer(self):
        self.operator_session()
        status, started = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": "owner@outlet.test", "mobile": "9800000013", "password": "Counter-outlet-1042", "role": "retailer"},
            origin=self.base,
        )
        self.assertEqual(status, 200)
        self.request(
            "POST",
            "/api/auth/signup/contact",
            {
                "signup_id": started["signup_id"],
                "email_code": self.verify.email_code,
                "sms_code": self.verify.sms_code,
            },
            origin=self.base,
        )
        self.verify.fail_link = True
        failed, _ = self.request(
            "POST",
            "/api/auth/signup/aadhaar",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(failed, 400)
        denied, _ = self.request(
            "POST",
            "/api/auth/login",
            {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"},
        )
        self.assertEqual(denied, 401)

    def test_same_email_can_open_the_other_role_after_verification(self):
        self.account("buyer@shop.test", "customer", "9800000014")
        self.account("buyer@shop.test", "retailer", "9800000014")
        customer, customer_body = self.request(
            "POST",
            "/api/auth/login",
            {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"},
        )
        self.assertEqual(customer, 200)
        self.assertEqual(customer_body["role"], "customer")

    def test_same_email_and_mobile_are_separate_users_per_role(self):
        self.account("shared@shop.test", "customer", "9811111111", password="Park-share-1111")
        self.account("shared@shop.test", "retailer", "9811111111", password="Park-share-2222")
        ok, retail = self.request(
            "POST",
            "/api/auth/login",
            {"email": "shared@shop.test", "password": "Park-share-2222", "role": "retailer"},
        )
        self.assertEqual(ok, 200)
        self.assertEqual(retail["role"], "retailer")
        denied, _ = self.request(
            "POST",
            "/api/auth/login",
            {"email": "shared@shop.test", "password": "Park-share-2222", "role": "customer"},
        )
        self.assertEqual(denied, 401)

    def test_operator_desk_lists_counts_without_opening_for_a_customer(self):
        created, _ = self.request(
            "POST",
            "/api/auth/register",
            {"email": "ops@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
        )
        self.assertEqual(created, 200)
        self.request("POST", "/api/auth/login", {"email": "ops@hub.test", "password": "Counter-outlet-1042", "role": "admin"})
        _, setup = self.request("POST", "/api/auth/mfa/setup", {})
        self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(setup["secret"])})
        status, desk = self.request("GET", "/api/auth/desk", origin=self.base)
        self.assertEqual(status, 200, desk)
        self.assertEqual(desk["counts"]["admin"], 1)
        self.assertEqual(desk["counts"]["customer"], 0)
        self.assertFalse(desk["signup_open"])
        self.assertNotIn("ip", desk["events"][0])
        self.account("buyer@shop.test", "customer", "9800000091")
        self.request("POST", "/api/auth/login", {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"})
        _, customer_setup = self.request("POST", "/api/auth/mfa/setup", {})
        self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(customer_setup["secret"])})
        denied, body = self.request("GET", "/api/auth/desk")
        self.assertEqual(denied, 403)
        self.assertEqual(body["error"], "Admin session required.")

    def test_operator_adds_the_next_operator_from_the_desk(self):
        self.operator_session()
        status, body = self.request(
            "POST",
            "/api/auth/desk/accounts",
            {"email": "desk@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(status, 200, body)
        public, message = self.request(
            "POST",
            "/api/auth/register",
            {"email": "third@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(public, 403)
        self.assertEqual(message["error"], "Admin signup is closed.")
        self.cookies = {}
        opened, login = self.request(
            "POST",
            "/api/auth/login",
            {"email": "desk@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(opened, 200, login)
        self.assertTrue(login.get("mfa_setup_required"))

    def test_operator_lists_people_and_can_close_sign_in(self):
        self.account("buyer@shop.test", "customer", "9800000092")
        self.operator_session()
        status, body = self.request("GET", "/api/auth/desk/people", origin=self.base)
        self.assertEqual(status, 200, body)
        listed = {person["email"]: person for person in body["people"]}
        self.assertIn("buyer@shop.test", listed)
        self.assertEqual(listed["buyer@shop.test"]["roles"], ["customer"])
        self.assertNotIn("password", json.dumps(body))
        self.assertNotIn("mfa_secret", json.dumps(body))
        closed, message = self.request(
            "POST",
            "/api/auth/desk/people/sign-in",
            {"email": "ops@hub.test", "enabled": False},
            origin=self.base,
        )
        self.assertEqual(closed, 400)
        self.assertIn("own sign-in", message["error"])
        blocked, _ = self.request(
            "POST",
            "/api/auth/desk/people/sign-in",
            {"email": "buyer@shop.test", "enabled": False},
            origin=self.base,
        )
        self.assertEqual(blocked, 200)
        self.cookies = {}
        denied, _ = self.request(
            "POST",
            "/api/auth/login",
            {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"},
        )
        self.assertEqual(denied, 401)

    def test_signup_list_hides_codes(self):
        self.operator_session()
        status, started = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": "owner@outlet.test", "mobile": "9800000093", "password": "Counter-outlet-1042", "role": "customer"},
            origin=self.base,
        )
        self.assertEqual(status, 200, started)
        listed, body = self.request("GET", "/api/auth/desk/signups", origin=self.base)
        self.assertEqual(listed, 200, body)
        self.assertEqual(body["pending"][0]["mobile_last4"], "0093")
        raw = json.dumps(body)
        self.assertNotIn(self.verify.email_code, raw)
        self.assertNotIn(self.verify.sms_code, raw)
        self.assertNotIn("9800000093", raw)

    def test_logs_keep_user_actions_apart_from_api_calls(self):
        from core.actions import log_action

        self.operator_session()
        log_action(
            action="integration.kaleyra.sms",
            outcome="error",
            status=401,
            duration_ms=4,
            target_id="parkpe:******0091",
            error_code="server_error",
            error_reason="otp=654321 api-key: unit-test-kaleyra-key",
        )
        status, body = self.request("GET", "/api/auth/desk/logs", origin=self.base)
        self.assertEqual(status, 200, body)
        events = [row["event"] for row in body["actions"]]
        self.assertIn("mfa_enabled", events)
        self.assertIn("register", events)
        self.assertTrue(all(row["service"] in {"Auth", "Signup"} for row in body["actions"]))
        self.assertTrue(all(row["id"].startswith("A-") and row["why"] for row in body["actions"]))
        self.assertTrue(all(row.get("request") and row.get("response") for row in body["actions"]))
        self.assertIn("The admin account was created.", [row["why"] for row in body["actions"] if row["event"] == "register"])
        match = next(row for row in body["api"] if row["action"] == "integration.kaleyra.sms")
        self.assertEqual(match["service"], "Kaleyra")
        self.assertRegex(match["id"], r"^S-\d+$")
        self.assertEqual(match["target_id"], "parkpe:******0091")
        self.assertEqual(match["why"], match["error_reason"])
        self.assertNotIn("654321", match["error_reason"])
        self.assertNotIn("654321", match["why"])
        self.assertNotIn("654321", match.get("request") or "")
        self.assertNotIn("654321", match.get("response") or "")
        raw = json.dumps(body)
        self.assertNotIn("unit-test-kaleyra-key", raw)
        self.assertNotIn("654321", raw)
        if self.operator_secret:
            self.assertNotIn(self.operator_secret, raw)

    def test_process_list_names_the_four_ports(self):
        self.operator_session()
        status, body = self.request("GET", "/api/auth/desk/processes", origin=self.base)
        self.assertEqual(status, 200, body)
        names = [row["name"] for row in body["processes"]]
        self.assertEqual(names, ["Auth", "ParkPe", "PaySwap", "API"])
        self.assertTrue(body["processes"][0]["up"])
        self.assertTrue(all(isinstance(row["up"], bool) for row in body["processes"]))
        self.assertEqual(body["processes"][0]["url"], "http://127.0.0.1:4600/")
        self.assertEqual(body["processes"][3]["url"], "http://127.0.0.1:4610/api/v1/health/")

    def test_services_lists_integrations_without_secrets(self):
        unauth, _ = self.request("GET", "/api/auth/desk/services", origin=self.base)
        self.assertEqual(unauth, 401)
        self.operator_session()
        status, body = self.request("GET", "/api/auth/desk/services", origin=self.base)
        self.assertEqual(status, 200, body)
        ids = [row["id"] for row in body["services"]]
        self.assertEqual(ids, ["kaleyra", "email", "cashfree", "hub_api", "bbps", "pg", "parking"])
        raw = json.dumps(body)
        self.assertNotIn("api_key", raw.lower())
        self.assertNotIn("secret", raw.lower())

    def test_operator_removes_a_role_but_not_their_own_admin(self):
        self.account("buyer@shop.test", "customer", "9800000094")
        self.operator_session()
        added, _ = self.request(
            "POST",
            "/api/auth/desk/accounts",
            {"email": "two@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(added, 200)
        own, message = self.request(
            "POST",
            "/api/auth/desk/people/role",
            {"email": "ops@hub.test", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(own, 400)
        self.assertIn("own admin", message["error"])
        removed, _ = self.request(
            "POST",
            "/api/auth/desk/people/role",
            {"email": "buyer@shop.test", "role": "customer"},
            origin=self.base,
        )
        self.assertEqual(removed, 200)
        self.cookies = {}
        denied, _ = self.request(
            "POST",
            "/api/auth/login",
            {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"},
        )
        self.assertEqual(denied, 401)

    def test_removed_retailer_can_sign_up_again(self):
        self.account("restart@outlet.test", "retailer", "9800000066")
        self.operator_session()
        listed, people = self.request("GET", "/api/auth/desk/people", origin=self.base)
        self.assertEqual(listed, 200, people)
        person = next(row for row in people["people"] if row["email"] == "restart@outlet.test")
        removed, body = self.request(
            "POST",
            "/api/auth/desk/people/role",
            {"user_id": person["id"], "role": "retailer"},
            origin=self.base,
        )
        self.assertEqual(removed, 200, body)
        started, again = self.request(
            "POST",
            "/api/auth/signup/start",
            {
                "email": "restart@outlet.test",
                "mobile": "9800000067",
                "password": "Counter-outlet-1042",
                "role": "retailer",
            },
            origin=self.base,
        )
        self.assertEqual(started, 200, again)

    def test_orphan_retailer_row_allows_signup_start(self):
        self.account("orphan@outlet.test", "retailer", "9800000070")
        user = self.app.store.user_by_email_role("orphan@outlet.test", "retailer")
        with self.app.store._lock:
            self.app.store._db.execute(
                "DELETE FROM memberships WHERE user_id = ? AND role = ?",
                (user["id"], "retailer"),
            )
            self.app.store._db.commit()
        self.operator_session()
        started, body = self.request(
            "POST",
            "/api/auth/signup/start",
            {
                "email": "orphan@outlet.test",
                "mobile": "9800000071",
                "password": "Counter-outlet-1042",
                "role": "retailer",
            },
            origin=self.base,
        )
        self.assertEqual(started, 200, body)

    def test_removed_role_drops_the_open_session(self):
        self.account("buyer@shop.test", "customer", "9800000099")
        self.cookies = {}
        self.request(
            "POST",
            "/api/auth/login",
            {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"},
        )
        saved = dict(self.cookies)
        self.operator_session()
        removed, _ = self.request(
            "POST",
            "/api/auth/desk/people/role",
            {"email": "buyer@shop.test", "role": "customer"},
            origin=self.base,
        )
        self.assertEqual(removed, 200)
        self.cookies = saved
        self.assertEqual(self.request("GET", "/api/auth/me")[0], 401)
        self.assertEqual(self.request("POST", "/api/auth/refresh", {})[0], 401)

    def test_operator_sets_a_password_and_resets_the_authenticator(self):
        self.account("buyer@shop.test", "customer", "9800000095")
        self.cookies = {}
        self.request(
            "POST",
            "/api/auth/login",
            {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"},
        )
        _, setup = self.request("POST", "/api/auth/mfa/setup", {})
        self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(setup["secret"])})
        self.operator_session()
        changed, body = self.request(
            "POST",
            "/api/auth/desk/people/password",
            {"email": "buyer@shop.test", "password": "Fresh-counter-2042"},
            origin=self.base,
        )
        self.assertEqual(changed, 200, body)
        self.assertNotIn("Fresh-counter-2042", json.dumps(body))
        reset, message = self.request(
            "POST",
            "/api/auth/desk/people/authenticator",
            {"email": "buyer@shop.test"},
            origin=self.base,
        )
        self.assertEqual(reset, 200, message)
        self.assertFalse(message["self"])
        self.cookies = {}
        opened, login = self.request(
            "POST",
            "/api/auth/login",
            {"email": "buyer@shop.test", "password": "Fresh-counter-2042", "role": "customer"},
        )
        self.assertEqual(opened, 200, login)
        self.assertTrue(login.get("mfa_setup_required"))

    def test_open_sessions_omit_token_hashes(self):
        self.operator_session()
        status, body = self.request(
            "GET",
            "/api/auth/desk/people/sessions?email=ops@hub.test",
            origin=self.base,
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["sessions"])
        bare = self.request("GET", "/api/auth/desk/people", origin="")
        self.assertEqual(bare[0], 200)
        blocked, message = self.request(
            "POST",
            "/api/auth/desk/people/role",
            {"email": "ops@hub.test", "role": "admin"},
            origin="",
        )
        self.assertEqual(blocked, 403)
        self.assertEqual(message["error"], "Admin session required.")
        raw = json.dumps(body)
        self.assertNotIn("refresh", raw)
        self.assertNotIn("token", raw)
        self.assertTrue(
            {"id", "role", "scope", "expires_at", "created_at"}.issubset(set(body["sessions"][0]))
        )

    def test_operator_can_cancel_and_resend_a_signup(self):
        self.operator_session()
        status, started = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": "owner@outlet.test", "mobile": "9800000096", "password": "Counter-outlet-1042", "role": "customer"},
            origin=self.base,
        )
        self.assertEqual(status, 200, started)
        first_email = self.verify.email_code
        resent, body = self.request(
            "POST",
            "/api/auth/signup/resend",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(resent, 200, body)
        self.assertNotIn(self.verify.email_code, json.dumps(body))
        self.assertNotEqual(first_email, self.verify.email_code)
        self.verify.send_email = lambda *_args: False
        failed, message = self.request(
            "POST",
            "/api/auth/signup/resend",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(failed, 503, message)
        cancelled, _ = self.request(
            "POST",
            "/api/auth/signup/cancel",
            {"signup_id": started["signup_id"]},
            origin=self.base,
        )
        self.assertEqual(cancelled, 200)
        listed, signups = self.request("GET", "/api/auth/desk/signups", origin=self.base)
        self.assertEqual(listed, 200)
        self.assertEqual(signups["pending"], [])

    def test_a_customer_cannot_read_the_product_desk(self):
        self.account("buyer@shop.test", "customer", "9800000097")
        self.cookies = {}
        self.request(
            "POST",
            "/api/auth/login",
            {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"},
            origin=self.base,
        )
        _, setup = self.request("POST", "/api/auth/mfa/setup", {}, origin=self.base)
        self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(setup["secret"])}, origin=self.base)
        status, body = self.request("GET", "/api/auth/desk/parkpe", origin=self.base)
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "Admin session required.")

    def test_product_desk_proxies_the_hub_and_reports_when_it_is_down(self):
        self.operator_session()

        class Hub(BaseHTTPRequestHandler):
            def do_GET(self):
                Hub.seen = self.path
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"sessions":[{"reference":"sess-proxied","state":"initiated"}]}')

            def log_message(self, *_args):
                return

        hub = ThreadingHTTPServer(("127.0.0.1", 0), Hub)
        thread = threading.Thread(target=hub.serve_forever, daemon=True)
        thread.start()
        previous = os.environ.get("HUB_API_ORIGIN")
        os.environ["HUB_API_ORIGIN"] = f"http://127.0.0.1:{hub.server_address[1]}"
        try:
            status, body = self.request("GET", "/api/auth/desk/parkpe", origin=self.base)
            self.assertEqual(status, 200, body)
            self.assertEqual(body["sessions"][0]["reference"], "sess-proxied")
            filtered, _ = self.request(
                "GET",
                "/api/auth/desk/parkpe?email=driver@parkpe.test",
                origin=self.base,
            )
            self.assertEqual(filtered, 200)
            self.assertIn("email=driver%40parkpe.test", Hub.seen)
            os.environ["HUB_API_ORIGIN"] = "http://127.0.0.1:9"
            down, message = self.request("GET", "/api/auth/desk/payswap", origin=self.base)
            self.assertEqual(down, 503, message)
            self.assertEqual(message["error"], "The hub API is not running.")
        finally:
            hub.shutdown()
            if previous is None:
                os.environ.pop("HUB_API_ORIGIN", None)
            else:
                os.environ["HUB_API_ORIGIN"] = previous

    def test_sub_admin_cannot_change_an_admin(self):
        self.operator_session()
        home, desk = self.request("GET", "/api/auth/desk", origin=self.base)
        self.assertEqual(home, 200, desk)
        self.assertTrue(desk["super"])
        added, _ = self.request(
            "POST",
            "/api/auth/desk/accounts",
            {"email": "desk@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(added, 200)
        self.cookies = {}
        self.request(
            "POST",
            "/api/auth/login",
            {"email": "desk@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        _, setup = self.request("POST", "/api/auth/mfa/setup", {}, origin=self.base)
        confirmed, _ = self.request(
            "POST",
            "/api/auth/mfa/confirm",
            {"code": totp_code(setup["secret"])},
            origin=self.base,
        )
        self.assertEqual(confirmed, 200)
        denied, message = self.request(
            "POST",
            "/api/auth/desk/accounts",
            {"email": "third@hub.test", "password": "Counter-outlet-1042", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(denied, 403)
        self.assertEqual(message["error"], "Only the super admin can add an admin.")
        removed, message = self.request(
            "POST",
            "/api/auth/desk/people/role",
            {"email": "ops@hub.test", "role": "admin"},
            origin=self.base,
        )
        self.assertEqual(removed, 403)
        self.assertEqual(message["error"], "Only the super admin can change an admin.")
        closed, message = self.request(
            "POST",
            "/api/auth/desk/people/sign-in",
            {"email": "ops@hub.test", "enabled": False},
            origin=self.base,
        )
        self.assertEqual(closed, 403)
        self.assertEqual(message["error"], "Only the super admin can change an admin.")
        password, message = self.request(
            "POST",
            "/api/auth/desk/people/password",
            {"email": "ops@hub.test", "password": "Fresh-counter-2042"},
            origin=self.base,
        )
        self.assertEqual(password, 403)
        self.assertEqual(message["error"], "Only the super admin can change an admin.")
        authenticator, message = self.request(
            "POST",
            "/api/auth/desk/people/authenticator",
            {"email": "ops@hub.test"},
            origin=self.base,
        )
        self.assertEqual(authenticator, 403)
        self.assertEqual(message["error"], "Only the super admin can change an admin.")

    def test_retailer_profile_stores_verification_metadata(self):
        self.account("vault@outlet.test", "retailer", "9800000077")
        self.operator_session()
        status, body = self.request(
            "GET",
            "/api/auth/desk/users/file?email=vault@outlet.test&role=retailer",
            origin=self.base,
        )
        self.assertEqual(status, 200, body)
        profile = next(row for row in body["profiles"] if row["role"] == "retailer")
        self.assertEqual(profile["pan_mask"], "ABCDE····F")
        self.assertEqual(profile["pan_name_hint"], "ParkPe User")
        self.assertTrue(profile["digilocker_ref"])
        self.assertEqual(profile["pan"], "ABCDE1234F")
        self.assertEqual(profile["pan_name"], "ParkPe User")
        self.assertEqual(profile["pan_registered_name"], "ParkPe User")
        self.assertEqual(profile["mobile"], "9800000077")
        self.assertTrue(profile["digilocker_verification_id"].startswith("pp"))

    def test_user_file_stores_full_kyc_fields_for_desk_file(self):
        self.account("buyer@shop.test", "customer", "9800000098")
        self.operator_session()
        status, body = self.request(
            "GET",
            "/api/auth/desk/users/file?email=buyer@shop.test",
            origin=self.base,
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["roles"], ["customer"])
        profile = body["profiles"][0]
        self.assertEqual(profile["mobile_last4"], "0098")
        self.assertEqual(profile["mobile"], "9800000098")
        self.assertTrue(profile["email_ok"])
        self.assertTrue(profile["mobile_ok"])
        self.assertFalse(profile["pan_ok"])
        self.assertNotIn("token", json.dumps(body))

    def _enrolled(self):
        self.account("owner@outlet.test", "retailer")
        self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        _, setup = self.request("POST", "/api/auth/mfa/setup", {})
        self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(setup["secret"])})
        return setup["secret"]


class KaleyraTests(unittest.TestCase):
    """integrations/kaleyra.py. The transport is local. No live Kaleyra call."""

    _ENV = (
        "KALEYRA_API_KEY",
        "KALEYRA_ACCOUNT_SID",
        "KALEYRA_SENDER_ID",
        "KALEYRA_OTP_TEMPLATE_ID",
        "KALEYRA_BASE_URL",
        "KALEYRA_SMS_PATH",
        "KALEYRA_TIMEOUT",
        "KALEYRA_OTP_BODY_TEMPLATE",
        "KALEYRA_PARKPE_SENDER_ID",
        "KALEYRA_PARKPE_TEMPLATE_ID",
        "KALEYRA_PARKPE_BODY",
        "KALEYRA_PAYSWAP_SENDER_ID",
        "KALEYRA_PAYSWAP_TEMPLATE_ID",
        "KALEYRA_PAYSWAP_BODY",
    )

    def setUp(self):
        self._saved = {name: os.environ.get(name) for name in self._ENV}
        for name in self._ENV:
            os.environ.pop(name, None)
        reset_action()

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reset_action()

    def _ready(self):
        os.environ["KALEYRA_API_KEY"] = "unit-test-kaleyra-key"
        os.environ["KALEYRA_ACCOUNT_SID"] = "HXINTESTS1"
        os.environ["KALEYRA_SENDER_ID"] = "TESTSEND"
        os.environ["KALEYRA_OTP_TEMPLATE_ID"] = "tmpl1"
        os.environ["KALEYRA_BASE_URL"] = "https://api.in.kaleyra.io"
        os.environ["KALEYRA_SMS_PATH"] = "messages"
        os.environ["KALEYRA_TIMEOUT"] = "10"

    def test_successful_dispatch_uses_the_configured_request(self):
        self._ready()
        seen = {}

        def transport(url, payload, headers, timeout):
            seen["url"] = url
            seen["payload"] = json.loads(payload)
            seen["headers"] = dict(headers)
            seen["timeout"] = timeout
            return 202, b'{"id":"msg-1","body":"otp 654321"}'

        bind_action(request_id="req-kaleyra-1", app_context="parkpe", actor="ops@hub.test", role="admin")
        with self.assertLogs("hub.actions", level="INFO") as captured:
            result = send_otp("91 98765 43210", "654321", transport=transport)
        self.assertTrue(result.ok)
        self.assertEqual(result.status, 202)
        self.assertEqual(seen["url"], "https://api.in.kaleyra.io/v1/HXINTESTS1/messages")
        self.assertEqual(seen["timeout"], 10.0)
        self.assertEqual(seen["headers"]["api-key"], "unit-test-kaleyra-key")
        self.assertEqual(seen["headers"]["Content-Type"], "application/json")
        self.assertEqual(seen["payload"]["to"], "+919876543210")
        self.assertEqual(seen["payload"]["sender"], "TESTSEND")
        self.assertEqual(seen["payload"]["type"], "OTP")
        self.assertEqual(seen["payload"]["channel"], "sms")
        self.assertEqual(seen["payload"]["template_id"], "tmpl1")
        self.assertIn("654321", seen["payload"]["body"])
        line = json.loads(captured.output[-1].split(":", 2)[-1])
        self.assertEqual(line["action"], "integration.kaleyra.sms")
        self.assertEqual(line["outcome"], "ok")
        self.assertEqual(line["status"], 202)
        self.assertEqual(line["request_id"], "req-kaleyra-1")
        self.assertEqual(line["app_context"], "parkpe")
        self.assertEqual(line["actor"], "ops@hub.test")
        self.assertEqual(line["role"], "admin")
        self.assertEqual(line["target_id"], "******3210")
        self.assertIn("POST https://api.in.kaleyra.io/v1/[sid]/messages", line["request"])
        self.assertIn("sender=TESTSEND", line["request"])
        self.assertIn("HTTP 202", line["response"])
        self.assertIn("msg-1", line["response"])
        self.assertNotIn("654321", line["request"])
        self.assertNotIn("654321", line["response"])
        text = "\n".join(captured.output)
        self.assertNotIn("654321", text)
        self.assertNotIn("unit-test-kaleyra-key", text)
        self.assertNotIn("HXINTESTS1", text)
        self.assertNotIn("9876543210", text)

    def test_missing_config_and_provider_failures_stay_generic(self):
        calls = []

        def transport(url, payload, headers, timeout):
            calls.append(url)
            return 200, b""

        os.environ["KALEYRA_API_KEY"] = "unit-test-kaleyra-key"
        with self.assertLogs("hub.actions", level="INFO") as captured:
            missing = send_otp("9876543210", "654321", transport=transport)
        self.assertFalse(missing.ok)
        self.assertEqual(missing.status, 503)
        self.assertEqual(missing.error_code, "server_error")
        self.assertEqual(missing.error_reason, "Kaleyra is not configured.")
        self.assertEqual(calls, [])
        self.assertNotIn("unit-test-kaleyra-key", missing.error_reason)
        self.assertNotIn("unit-test-kaleyra-key", "\n".join(captured.output))

        self._ready()
        os.environ["KALEYRA_BASE_URL"] = "http://unit-test-kaleyra-key.example/v1"
        with self.assertLogs("hub.actions", level="INFO") as captured:
            bad_url = send_otp("9876543210", "654321", transport=transport)
        self.assertEqual(bad_url.error_reason, "Kaleyra is not configured.")
        self.assertNotIn("unit-test-kaleyra-key", bad_url.error_reason)
        self.assertNotIn("unit-test-kaleyra-key", "\n".join(captured.output))
        self.assertEqual(calls, [])

        self._ready()

        def timed_out(url, payload, headers, timeout):
            raise TimeoutError

        with self.assertLogs("hub.actions", level="INFO") as captured:
            slow = send_otp("9876543210", "654321", transport=timed_out)
        self.assertFalse(slow.ok)
        self.assertEqual(slow.status, 504)
        self.assertEqual(slow.error_reason, "Kaleyra did not respond.")
        self.assertNotIn("654321", "\n".join(captured.output))

        def rejected(url, payload, headers, timeout):
            return 401, b'{"api-key":"unit-test-kaleyra-key","otp":"654321","sid":"HXINTESTS1"}'

        with self.assertLogs("hub.actions", level="INFO") as captured:
            denied = send_otp("9876543210", "654321", transport=rejected)
        self.assertFalse(denied.ok)
        self.assertEqual(denied.status, 401)
        self.assertEqual(denied.error_code, "server_error")
        self.assertEqual(denied.error_reason, "Kaleyra rejected the message.")
        text = "\n".join(captured.output)
        for secret in ("654321", "unit-test-kaleyra-key", "HXINTESTS1", "9876543210"):
            self.assertNotIn(secret, denied.error_reason)
            self.assertNotIn(secret, text)

        def down(url, payload, headers, timeout):
            raise urllib.error.URLError("network down")

        with self.assertLogs("hub.actions", level="INFO"):
            offline = send_otp("9876543210", "654321", transport=down)
        self.assertEqual(offline.status, 503)
        self.assertEqual(offline.error_reason, "Kaleyra is not reachable.")

    def test_redaction_strips_otp_and_api_key(self):
        leaked = redact(
            {
                "api_key": "unit-test-kaleyra-key",
                "api-key": "unit-test-kaleyra-key",
                "sid": "HXINTESTS1",
                "otp": "654321",
                "note": "api-key: unit-test-kaleyra-key otp: 654321",
                "target_id": "******3210",
            }
        )
        raw = json.dumps(leaked)
        self.assertEqual(leaked["target_id"], "******3210")
        self.assertNotIn("unit-test-kaleyra-key", raw)
        self.assertNotIn("654321", raw)
        self.assertNotIn("HXINTESTS1", raw)
        self.assertIn("[redacted]", raw)

        self._ready()
        calls = []

        def transport(url, payload, headers, timeout):
            calls.append(url)
            return 202, b""

        previous = kaleyra.urllib_post
        kaleyra.urllib_post = transport
        try:
            with self.assertLogs("hub.actions", level="INFO") as captured:
                bad_code = send_otp("9876543210", "654321-and-more", transport=transport)
                sent = LiveVerify().send_sms("9876543210", "654321")
        finally:
            kaleyra.urllib_post = previous
        self.assertFalse(bad_code.ok)
        self.assertEqual(bad_code.error_reason, "Check the code.")
        self.assertTrue(sent)
        self.assertEqual(calls, ["https://api.in.kaleyra.io/v1/HXINTESTS1/messages"])
        text = "\n".join(captured.output)
        self.assertNotIn("654321", text)
        self.assertNotIn("unit-test-kaleyra-key", text)
        self.assertNotIn("654321-and-more", text)

    def test_customer_and_retailer_use_separate_templates(self):
        os.environ["KALEYRA_API_KEY"] = "unit-test-kaleyra-key"
        os.environ["KALEYRA_ACCOUNT_SID"] = "HXINTESTS1"
        os.environ["KALEYRA_BASE_URL"] = "https://api.in.kaleyra.io"
        os.environ["KALEYRA_PARKPE_SENDER_ID"] = "PARKPA"
        os.environ["KALEYRA_PARKPE_TEMPLATE_ID"] = "1007875005613696432"
        os.environ["KALEYRA_PARKPE_BODY"] = (
            "Dear Customer, your OTP for registration on Parkpe is {#numeric#}. "
            "Please do not share this OTP with anyone. - PFPL"
        )
        os.environ["KALEYRA_PAYSWAP_SENDER_ID"] = "PYSWAP"
        os.environ["KALEYRA_PAYSWAP_TEMPLATE_ID"] = "1007640321725099860"
        os.environ["KALEYRA_PAYSWAP_BODY"] = (
            "Dear User, Your one time password for Payswap registration is {#var#}. "
            "Please do not share this OTP any one. Powered by PAYSWAP"
        )
        seen = []

        def transport(url, payload, headers, timeout):
            seen.append(json.loads(payload))
            return 202, b""

        with self.assertLogs("hub.actions", level="INFO") as captured:
            customer = send_otp("9876543210", "654321", transport=transport, role="customer")
            retailer = send_otp("9876543210", "654321", transport=transport, role="retailer")
        self.assertTrue(customer.ok)
        self.assertTrue(retailer.ok)
        self.assertEqual(seen[0]["sender"], "PARKPA")
        self.assertEqual(seen[0]["template_id"], "1007875005613696432")
        self.assertIn("is 654321.", seen[0]["body"])
        self.assertNotIn("{#numeric#}", seen[0]["body"])
        self.assertEqual(seen[1]["sender"], "PYSWAP")
        self.assertEqual(seen[1]["template_id"], "1007640321725099860")
        self.assertIn("is 654321.", seen[1]["body"])
        self.assertNotIn("{#var#}", seen[1]["body"])
        text = "\n".join(captured.output)
        self.assertIn("parkpe:******3210", text)
        self.assertIn("payswap:******3210", text)
        self.assertNotIn("654321", text)
        self.assertNotIn("unit-test-kaleyra-key", text)
        self.assertNotIn("HXINTESTS1", text)

    def test_local_env_does_not_override_or_read_other_names(self):
        folder = tempfile.TemporaryDirectory()
        path = Path(folder.name) / "kaleyra.env"
        path.write_text(
            "\n".join(
                [
                    "# local only",
                    "KALEYRA_API_KEY=file-key",
                    "KALEYRA_SENDER_ID=FROMFILE",
                    "PATH=/tmp/not-used",
                    "",
                ]
            )
        )
        os.environ["KALEYRA_API_KEY"] = "already-set"
        load_local_env(path)
        self.assertEqual(os.environ["KALEYRA_API_KEY"], "already-set")
        self.assertEqual(os.environ["KALEYRA_SENDER_ID"], "FROMFILE")
        self.assertNotEqual(os.environ.get("PATH"), "/tmp/not-used")
        folder.cleanup()


class MailEnvTests(unittest.TestCase):
    def test_mail_env_does_not_override_or_read_other_names(self):
        folder = tempfile.TemporaryDirectory()
        path = Path(folder.name) / "mail.env"
        path.write_text(
            "\n".join(
                [
                    "AUTH_MAIL_CONFIG=/tmp/from-file.php",
                    "AUTH_SES_SMTP_PHP=/tmp/smtp-from-file.php",
                    "KALEYRA_API_KEY=not-this-file",
                    "",
                ]
            )
        )
        previous = {name: os.environ.get(name) for name in ("AUTH_MAIL_CONFIG", "AUTH_SES_SMTP_PHP", "KALEYRA_API_KEY")}
        os.environ["AUTH_MAIL_CONFIG"] = "/tmp/already-set.php"
        os.environ.pop("AUTH_SES_SMTP_PHP", None)
        os.environ.pop("KALEYRA_API_KEY", None)
        try:
            load_mail_env(path)
            self.assertEqual(os.environ["AUTH_MAIL_CONFIG"], "/tmp/already-set.php")
            self.assertEqual(os.environ["AUTH_SES_SMTP_PHP"], "/tmp/smtp-from-file.php")
            self.assertNotIn("KALEYRA_API_KEY", os.environ)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            folder.cleanup()


class ProfileAndSessionTests(AuthTests):
    def test_profile_update_password_change_and_session_revoke(self):
        self.account("member@parkpe.test", "customer", "9800000123", "Initial-Secret-9911")
        code, login_body = self.request(
            "POST",
            "/api/auth/login",
            {"email": "member@parkpe.test", "password": "Initial-Secret-9911", "role": "customer"},
            origin=self.base,
        )
        self.assertEqual(code, 200, login_body)
        _, setup = self.request("POST", "/api/auth/mfa/setup", {}, origin=self.base)
        secret = setup["secret"]
        confirmed, _ = self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(secret)}, origin=self.base)
        self.assertEqual(confirmed, 200)

        st, prof = self.request("GET", "/api/auth/profile", origin=self.base)
        self.assertEqual(st, 200, prof)
        self.assertEqual(prof["profile"]["email"], "member@parkpe.test")

        st, upd = self.request(
            "POST",
            "/api/auth/profile",
            {"display_name": "Aarav Mehta", "city": "Gurugram", "address": "DLF Phase 2"},
            origin=self.base,
        )
        self.assertEqual(st, 200, upd)
        self.assertEqual(upd["profile"]["display_name"], "Aarav Mehta")
        self.assertEqual(upd["profile"]["city"], "Gurugram")

        st, me = self.request("GET", "/api/auth/me", origin=self.base)
        self.assertEqual(st, 200)
        self.assertEqual(me["display_name"], "Aarav Mehta")

        st, sess = self.request("GET", "/api/auth/sessions", origin=self.base)
        self.assertEqual(st, 200, sess)
        self.assertGreaterEqual(len(sess["sessions"]), 1)
        self.assertTrue(any(s["current"] for s in sess["sessions"]))

        st_rev, rev = self.request("POST", "/api/auth/sessions/revoke", {}, origin=self.base)
        self.assertEqual(st_rev, 200, rev)
        self.assertTrue(rev.get("ok"))

        st, chg = self.request(
            "POST",
            "/api/auth/password/change",
            {"current_password": "Initial-Secret-9911", "new_password": "Updated-Secret-8822"},
            origin=self.base,
        )
        self.assertEqual(st, 200, chg)

        # Sign in again with new password + MFA
        self.cookies = {}
        st, relogin = self.request(
            "POST",
            "/api/auth/login",
            {"email": "member@parkpe.test", "password": "Updated-Secret-8822", "role": "customer"},
            origin=self.base,
        )
        self.assertEqual(st, 200, relogin)
        st2, mfa2 = self.request("POST", "/api/auth/mfa", {"code": _next_totp(secret)}, origin=self.base)
        self.assertEqual(st2, 200, mfa2)

    def test_same_device_relogin_reuses_one_session_family(self):
        self.account("browser@parkpe.test", "customer", "9800000999", "Session-Secret-4411")
        device = "device-test-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        code, login_body = self.request(
            "POST",
            "/api/auth/login",
            {
                "email": "browser@parkpe.test",
                "password": "Session-Secret-4411",
                "role": "customer",
                "device_id": device,
            },
            origin=self.base,
        )
        self.assertEqual(code, 200, login_body)
        _, setup = self.request("POST", "/api/auth/mfa/setup", {}, origin=self.base)
        secret = setup["secret"]
        backups = list(setup.get("backup_codes") or [])
        self.assertGreaterEqual(len(backups), 2, setup)
        confirmed, _ = self.request(
            "POST",
            "/api/auth/mfa/confirm",
            {"code": totp_code(secret), "device_id": device},
            origin=self.base,
        )
        self.assertEqual(confirmed, 200)

        st, first = self.request("GET", "/api/auth/sessions", origin=self.base)
        self.assertEqual(st, 200, first)
        self.assertEqual(len(first["sessions"]), 1)
        self.assertTrue(first["sessions"][0]["device_bound"])

        # Second MFA login on the same device_id must not stack another open session.
        self.cookies = {}
        st, again = self.request(
            "POST",
            "/api/auth/login",
            {
                "email": "browser@parkpe.test",
                "password": "Session-Secret-4411",
                "role": "customer",
                "device_id": device,
            },
            origin=self.base,
        )
        self.assertEqual(st, 200, again)
        self.assertTrue(again.get("mfa_required"))
        st2, mfa2 = self.request(
            "POST",
            "/api/auth/mfa",
            {"code": backups[0], "device_id": device},
            origin=self.base,
        )
        self.assertEqual(st2, 200, mfa2)
        st, second = self.request("GET", "/api/auth/sessions", origin=self.base)
        self.assertEqual(st, 200, second)
        self.assertEqual(len(second["sessions"]), 1, second)

        # A different browser id is a second device family.
        other = "device-test-zzzzzzzz-yyyy-xxxx-wwww-vvvvvvvvvvvv"
        self.cookies = {}
        self.request(
            "POST",
            "/api/auth/login",
            {
                "email": "browser@parkpe.test",
                "password": "Session-Secret-4411",
                "role": "customer",
                "device_id": other,
            },
            origin=self.base,
        )
        st_mfa, mfa_other = self.request(
            "POST",
            "/api/auth/mfa",
            {"code": backups[1], "device_id": other},
            origin=self.base,
        )
        self.assertEqual(st_mfa, 200, mfa_other)
        st, both = self.request("GET", "/api/auth/sessions", origin=self.base)
        self.assertEqual(st, 200, both)
        self.assertEqual(len(both["sessions"]), 2, both)


if __name__ == "__main__":
    unittest.main()
