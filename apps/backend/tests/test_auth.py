import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from http.server import ThreadingHTTPServer

from auth.security import totp_code
from auth.server import AuthApp, build_handler


class FakeVerify:
    def __init__(self):
        self.email_code = ""
        self.sms_code = ""
        self.fail_link = False
        self.last_id = ""

    def send_email(self, to, code):
        self.email_code = code
        return True

    def send_sms(self, mobile, code):
        self.sms_code = code
        return True

    def digilocker_link(self, verification_id):
        if self.fail_link:
            return None
        self.last_id = verification_id
        return "https://verification.example/dgl/test"

    def digilocker_ok(self, verification_id):
        return verification_id == self.last_id and not self.fail_link

    def pan_check(self, pan, name):
        return pan == "ABCDE1234F" and len(name) >= 2


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
                {"code": totp_code(self.operator_secret)},
                origin=self.base,
            )
            self.assertEqual(confirmed, 200)

    def account(self, email, role, mobile="9800000010"):
        me_status, me = self.request("GET", "/api/auth/me", origin=self.base)
        if me_status != 200 or me.get("role") != "admin":
            self.operator_session()
        status, started = self.request(
            "POST",
            "/api/auth/signup/start",
            {"email": email, "mobile": mobile, "password": "Counter-outlet-1042", "role": role},
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
        passed, user = self.request("POST", "/api/auth/mfa", {"code": totp_code(setup["secret"])})
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
        self.request("POST", "/api/auth/mfa", {"code": totp_code(secret)})
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
            self.assertIn("People", page)
            self.assertIn("Verification", page)
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
        self.assertEqual(body["signups"][0]["mobile_last4"], "0093")
        raw = json.dumps(body)
        self.assertNotIn(self.verify.email_code, raw)
        self.assertNotIn(self.verify.sms_code, raw)
        self.assertNotIn("9800000093", raw)

    def test_process_list_names_the_four_ports(self):
        self.operator_session()
        status, body = self.request("GET", "/api/auth/desk/processes", origin=self.base)
        self.assertEqual(status, 200, body)
        names = [row["name"] for row in body["processes"]]
        self.assertEqual(names, ["Auth", "ParkPe", "PaySwap", "API"])
        self.assertTrue(body["processes"][0]["up"])
        self.assertTrue(all(isinstance(row["up"], bool) for row in body["processes"]))

    def _enrolled(self):
        self.account("owner@outlet.test", "retailer")
        self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        _, setup = self.request("POST", "/api/auth/mfa/setup", {})
        self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(setup["secret"])})
        return setup["secret"]


if __name__ == "__main__":
    unittest.main()
