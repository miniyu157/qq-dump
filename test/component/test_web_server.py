"""web.server: 本地 WebUI 的访问控制、接口与退出。

判定基准: HTTP 状态码、响应头与手写的期望数据 (support.profile)。服务监听系统分配的回环端口。
替身: service.avatars 的 prepare_cache 与 avatar (公开接口)，不建缓存目录，不访问网络。
"""

import http.client
import json
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from support import REPO
from support.cli import child_env
from support.profile import FRIENDS, OWNER, write_profile

from web.server import create_server

__all__ = []

_PNG = b"\x89PNG\r\n\x1a\n fake image"


class _Response:
    def __init__(self, response: http.client.HTTPResponse) -> None:
        self.status = response.status
        self.headers = response.headers
        self.body = response.read()


class _ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        profile = Path(temporary.name) / "profile_info.db"
        write_profile(profile)

        cls.avatar_calls = []

        def fake_avatar(uin: str) -> tuple[bytes, str] | None:
            cls.avatar_calls.append(uin)
            return None if uin == "20002" else (_PNG, "image/png")

        for replacement in (patch("web.server.prepare_cache"), patch("web.server.avatar", fake_avatar)):
            replacement.start()
            cls.addClassCleanup(replacement.stop)

        cls.server = create_server(str(profile), port=0)
        cls.port = cls.server.server_address[1]
        cls.token = cls.server.token
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)

    def request(self, method: str, path: str, *, cookie: str | None = "valid", host: str | None = None, body: bytes | None = None, headers: dict[str, str] | None = None) -> _Response:
        """cookie 为 "valid" 时带上正确的凭据，为 None 时不带，其余取值原样作为 token。

        会在读取请求体之前被拒绝的 POST (凭据、Host 或路径不符) 不要带请求体: 服务端丢下未读的请求体关闭连接时，
        客户端可能收到连接中断而不是状态码 (见 test/README.md 的已知问题)，用例会因此时过时不过。
        """
        send = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
        if cookie is not None:
            send["Cookie"] = f"qqdump_token={self.token if cookie == 'valid' else cookie}"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=send)
            return _Response(conn.getresponse())
        finally:
            conn.close()


class AccessControlTests(_ServerCase):
    """回环地址对本机其他程序和恶意网页同样可达: 请求必须发往本服务的地址，并带有启动时生成的 token。"""

    def test_token_in_the_start_url_is_exchanged_for_a_cookie(self) -> None:
        response = self.request("GET", f"/?token={self.token}", cookie=None)
        self.assertEqual((response.status, response.headers["Location"]), (303, "/"))
        cookie = response.headers["Set-Cookie"]
        self.assertTrue(cookie.startswith(f"qqdump_token={self.token};"))
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_cookie_opens_the_page(self) -> None:
        response = self.request("GET", "/")
        self.assertEqual((response.status, response.headers["Content-Type"]), (200, "text/html; charset=utf-8"))
        self.assertEqual(response.body, (REPO / "web" / "static" / "index.html").read_bytes())

    def test_requests_without_valid_credentials_are_refused(self) -> None:
        refused = {
            "没有凭据": ("GET", "/", None),
            "URL 中的 token 错误": ("GET", "/?token=wrong", None),
            "Cookie 中的 token 错误": ("GET", "/", "wrong"),
            "token 是正确值的前缀": ("GET", "/", self.token[:-1]),
            "接口没有凭据": ("GET", "/api/friends", None),
            "静态文件没有凭据": ("GET", "/app.js", None),
            "token 只在首页的 URL 中有效": ("GET", f"/api/friends?token={self.token}", None),
            "POST 没有凭据": ("POST", "/api/jobs", None),
        }
        for reason, (method, path, cookie) in refused.items():
            with self.subTest(reason=reason):
                self.assertEqual(self.request(method, path, cookie=cookie).status, 403)

    def test_requests_addressed_to_another_host_are_refused_despite_valid_credentials(self) -> None:
        # DNS rebinding: 恶意网页把自己的域名解析到 127.0.0.1，浏览器发来的 Host 仍是那个域名
        for host in ("evil.example", f"evil.example:{self.port}", f"127.0.0.1:{self.port + 1}", "127.0.0.1", f"LOCALHOST.evil.example:{self.port}"):
            for method, path in (("GET", "/api/friends"), ("GET", f"/?token={self.token}"), ("POST", "/api/jobs")):
                with self.subTest(host=host, method=method, path=path):
                    self.assertEqual(self.request(method, path, host=host).status, 403)

    def test_localhost_name_is_accepted(self) -> None:
        self.assertEqual(self.request("GET", "/api/owner", host=f"localhost:{self.port}").status, 200)

    def test_each_server_gets_its_own_unguessable_token(self) -> None:
        with patch("web.server.prepare_cache"):
            other = create_server(str(Path(self.server_profile())), port=0)
        try:
            self.assertNotEqual(other.token, self.token)
            self.assertGreaterEqual(len(other.token), 32)
        finally:
            other.server_close()

    def server_profile(self) -> str:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        profile = Path(temporary.name) / "profile_info.db"
        write_profile(profile)
        return str(profile)


class DataTests(_ServerCase):
    def _json(self, path: str) -> object:
        response = self.request("GET", path)
        self.assertEqual((response.status, response.headers["Content-Type"], response.headers["Cache-Control"]), (200, "application/json; charset=utf-8", "no-store"))
        return json.loads(response.body)

    def test_friends(self) -> None:
        self.assertEqual(self._json("/api/friends"), FRIENDS)

    def test_owner(self) -> None:
        self.assertEqual(self._json("/api/owner"), OWNER)

    def test_avatar_of_a_listed_account(self) -> None:
        response = self.request("GET", "/api/avatar/21001")
        self.assertEqual((response.status, response.headers["Content-Type"], response.body), (200, "image/png", _PNG))

    def test_avatar_of_the_owner(self) -> None:
        self.assertEqual(self.request("GET", "/api/avatar/10001").status, 200)

    def test_avatar_that_cannot_be_obtained(self) -> None:
        self.assertEqual(self.request("GET", "/api/avatar/20002").status, 404)

    def test_avatar_of_an_account_outside_the_database_is_never_fetched(self) -> None:
        # 否则本服务可被用来向头像接口请求任意号码
        for uin in ("99999", "abc", ""):
            with self.subTest(uin=uin):
                self.avatar_calls.clear()
                self.assertEqual(self.request("GET", f"/api/avatar/{uin}").status, 404)
                self.assertEqual(self.avatar_calls, [])


class StaticFileTests(_ServerCase):
    def test_assets_are_served_with_their_types(self) -> None:
        for name, content_type in (("app.js", "text/javascript; charset=utf-8"), ("style.css", "text/css; charset=utf-8")):
            with self.subTest(name=name):
                response = self.request("GET", f"/{name}")
                self.assertEqual((response.status, response.headers["Content-Type"]), (200, content_type))
                self.assertEqual(response.body, (REPO / "web" / "static" / name).read_bytes())

    def test_missing_file(self) -> None:
        self.assertEqual(self.request("GET", "/absent.js").status, 404)

    def test_paths_leaving_the_static_directory_are_not_served(self) -> None:
        for path in ("/../server.py", "/../../main.py", "/vendor/../../server.py", "//../server.py", "/..", "/."):
            with self.subTest(path=path):
                response = self.request("GET", path)
                self.assertEqual(response.status, 404)
                self.assertNotIn(b"def create_server", response.body)


class JobRequestTests(_ServerCase):
    def _post(self, body: bytes, *, path: str = "/api/jobs", headers: dict[str, str] | None = None) -> int:
        return self.request("POST", path, body=body, headers=headers).status

    def test_well_formed_request_reaches_the_unimplemented_operation(self) -> None:
        self.assertEqual(self._post(json.dumps({"op": "export", "uids": ["u_friend_a"]}).encode()), 501)

    def test_malformed_requests_are_rejected(self) -> None:
        rejected = {
            "不是 JSON": b"not json",
            "不是对象": b"[]",
            "缺少 uids": b'{"op": "export"}',
            "uids 不是数组": b'{"uids": "u_friend_a"}',
            "uids 含非文本": b'{"uids": ["u_friend_a", 1]}',
        }
        for reason, body in rejected.items():
            with self.subTest(reason=reason):
                self.assertEqual(self._post(body), 400)

    def test_invalid_content_length(self) -> None:
        self.assertEqual(self._post(b"", headers={"Content-Length": "abc"}), 400)

    def test_oversized_body_is_refused_before_it_is_read(self) -> None:
        self.assertEqual(self._post(b"", headers={"Content-Length": str(64 * 1024 + 1)}), 413)

    def test_unknown_path(self) -> None:
        self.assertEqual(self._post(b"", path="/api/other"), 404)


class ServeTests(unittest.TestCase):
    def test_interrupt_ends_the_blocking_serve_call(self) -> None:
        # 回归: Windows 上主线程曾停在无超时的 join 里，收不到 Ctrl+C。挂死时本用例无法自行脱身，故放进子进程并限时
        with TemporaryDirectory() as directory:
            profile = Path(directory) / "profile_info.db"
            write_profile(profile)
            driver = "\n".join([
                "import signal, sys, threading",
                "from unittest.mock import patch",
                f"sys.path.insert(0, {str(REPO)!r})",
                "from web.server import serve",
                "threading.Timer(1.0, signal.raise_signal, [signal.SIGINT]).start()",
                "with patch('web.server.prepare_cache'):",
                f"    serve({str(profile)!r}, port=0)",
                "print('serve returned')",
            ])
            try:
                done = subprocess.run([sys.executable, "-c", driver], stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", env=child_env(), timeout=30, check=False)
            except subprocess.TimeoutExpired:
                self.fail("serve() 在收到中断信号后 30 秒内没有返回")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("serve returned", done.stdout)


if __name__ == "__main__":
    unittest.main()
