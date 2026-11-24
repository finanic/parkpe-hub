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


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = AuthApp(
            data_dir=Path(self.tmp.name),
            origins={"http://127.0.0.1:4500"},
            scrypt_n=2**12,
            cookie_secure=False,
            samesite="Lax",
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.cookies = {}

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

    def test_login_hides_whether_the_email_exists(self):
        missing = self.request("POST", "/api/auth/login", {"email": "no@outlet.test", "password": "not-a-real-pass", "role": "retailer"})
        self.request("POST", "/api/auth/register", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        wrong = self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "not-a-real-pass", "role": "retailer"})
        self.assertEqual(missing, wrong)
        self.assertNotIn("auth_access", self.cookies)

    def test_customer_password_does_not_open_the_retailer_counter(self):
        self.request("POST", "/api/auth/register", {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "customer"})
        status, body = self.request("POST", "/api/auth/login", {"email": "buyer@shop.test", "password": "Counter-outlet-1042", "role": "retailer"})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "Email or password is incorrect.")

    def test_counter_stays_closed_until_authenticator_is_on(self):
        self.request("POST", "/api/auth/register", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
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
        self.request("POST", "/api/auth/register", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
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
        status, body = self.request("GET", "/api/auth/setup")
        self.assertEqual(status, 200)
        self.assertTrue(body["signup_open"])
        created, _ = self.request(
            "POST",
            "/api/auth/register",
            {"email": "ops@hub.test", "password": "Counter-outlet-1042", "role": "operator"},
        )
        self.assertEqual(created, 200)
        closed, message = self.request(
            "POST",
            "/api/auth/register",
            {"email": "second@hub.test", "password": "Counter-outlet-1042", "role": "operator"},
        )
        self.assertEqual(closed, 403)
        self.assertEqual(message["error"], "Operator signup is closed.")
        retailer, _ = self.request(
            "POST",
            "/api/auth/register",
            {"email": "shop@hub.test", "password": "Counter-outlet-1042", "role": "retailer"},
        )
        self.assertEqual(retailer, 200)
        denied, body = self.request(
            "POST",
            "/api/auth/login",
            {"email": "shop@hub.test", "password": "Counter-outlet-1042", "role": "operator"},
        )
        self.assertEqual(denied, 401)
        self.assertEqual(body["error"], "Email or password is incorrect.")

    def test_short_password_is_rejected(self):
        status, body = self.request("POST", "/api/auth/register", {"email": "owner@outlet.test", "password": "short", "role": "retailer"})
        self.assertEqual(status, 400)
        self.assertIn("12", body["error"])

    def _enrolled(self):
        self.request("POST", "/api/auth/register", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        self.request("POST", "/api/auth/login", {"email": "owner@outlet.test", "password": "Counter-outlet-1042", "role": "retailer"})
        _, setup = self.request("POST", "/api/auth/mfa/setup", {})
        self.request("POST", "/api/auth/mfa/confirm", {"code": totp_code(setup["secret"])})
        return setup["secret"]


if __name__ == "__main__":
    unittest.main()
