"""QQ DUMP WebUI：本地 HTTP 服务、静态页面与 JSON 接口。"""

import errno
import hmac
import json
import secrets
import subprocess
import sys
import threading
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from api import load_friends, load_owner
from app.ansi import out
from app.utils import good_log, prefer_binaries
from service.avatars import avatar, prepare_cache

HOST = "127.0.0.1"
PORT = 40080

# 回环地址对本机其他程序与经 DNS rebinding 的网页同样可达：Host 必须是本服务的地址，
# 且请求需带启动时生成的 token。token 经首次打开的 URL 传入，换成 SameSite=Strict 的 Cookie 后不再出现在地址栏
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
TOKEN_COOKIE = "qqdump_token"

# POST 请求体上限
MAX_BODY = 64 * 1024

STATIC = (Path(__file__).resolve().parent / "static").resolve()
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


class Server(ThreadingHTTPServer):
    """客户端提前断开属于常态，不作为服务端异常记录；token 为本次启动的访问凭据"""

    token: str

    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


def create_server(profile_db: str, nt_db: str | None = None) -> ThreadingHTTPServer:
    """创建固定端口的回环服务；nt_db 预留给后续任务"""
    prepare_cache()
    friends = [friend._asdict() for friend in load_friends(profile_db)]
    uins = {str(friend["uin"]) for friend in friends if friend["uin"] is not None}
    owner = load_owner(profile_db)
    if owner is not None and owner.uin is not None:
        uins.add(str(owner.uin))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlsplit(self.path)
            if not self._host_allowed():
                return
            if url.path == "/" and self._token_matches(parse_qs(url.query).get("token", [""])[0]):
                self._grant_cookie()
                return
            if not self._token_matches(self._cookie_token()):
                # message 写入状态行，只能是 latin-1；中文说明放进 explain，随响应体输出
                self.send_error(HTTPStatus.FORBIDDEN, explain="请使用启动时输出的地址打开页面")
                return
            if url.path == "/":
                self._file(STATIC / "index.html")
            elif url.path == "/api/friends":
                self._json(HTTPStatus.OK, friends)
            elif url.path == "/api/owner":
                self._json(HTTPStatus.OK, owner._asdict() if owner is not None else None)
            elif url.path.startswith("/api/avatar/"):
                self._avatar(url.path.rsplit("/", 1)[-1])
            else:
                self._static(url.path)

        def do_POST(self) -> None:
            url = urlsplit(self.path)
            if not self._host_allowed():
                return
            if not self._token_matches(self._cookie_token()):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if url.path != "/api/jobs":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Content-Length 无效"})
                return
            if length > MAX_BODY:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"请求体超过 {MAX_BODY} 字节"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "请求体不是合法 JSON"})
                return
            if not isinstance(body, dict):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "请求体必须是 JSON 对象"})
                return
            if not isinstance(body.get("uids"), list) or not all(isinstance(uid, str) for uid in body["uids"]):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "uids 必须是字符串数组"})
                return
            # 下一个 API 尚未实现，先固定返回 501
            self._json(HTTPStatus.NOT_IMPLEMENTED, {"error": f"操作尚未实现: {body.get('op')}"})

        def _host_allowed(self) -> bool:
            """Host 不是本服务地址时返回 403，阻断 DNS rebinding"""
            if self.headers.get("Host") in ALLOWED_HOSTS:
                return True
            self.send_error(HTTPStatus.FORBIDDEN)
            return False

        def _token_matches(self, candidate: str) -> bool:
            return bool(candidate) and hmac.compare_digest(candidate, self.server.token)

        def _cookie_token(self) -> str:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            morsel = cookie.get(TOKEN_COOKIE)
            return morsel.value if morsel else ""

        def _grant_cookie(self) -> None:
            """token 换成 Cookie 后重定向到不含 token 的地址"""
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Set-Cookie", f"{TOKEN_COOKIE}={self.server.token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _avatar(self, uin: str) -> None:
            if uin not in uins:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            result = avatar(uin)
            if result is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data, content_type = result
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: HTTPStatus, payload: object) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _static(self, request_path: str) -> None:
            target = (STATIC / request_path.lstrip("/")).resolve()
            if STATIC not in target.parents:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._file(target)

        def _file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", TYPES.get(path.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    server = Server((HOST, PORT), Handler)
    server.token = secrets.token_urlsafe(32)
    return server


def serve(profile_db: str, nt_db: str | None = None) -> None:
    """启动 WebUI，等待回车打开页面，阻塞到 Ctrl+C"""
    try:
        server = create_server(profile_db, nt_db)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit(f"端口 {PORT} 已被占用") from exc
        raise

    host, port = server.server_address
    url = f"http://{host}:{port}/?token={server.token}"
    if out.TTY:
        print("\033[2J\033[H", end="", flush=True)
    print(f"{out.BOLD}QQ DUMP WebUI{out.RESET}")
    good_log(url)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        # 缺少 xdg-open 时只提示，不等待回车，直接进入服务阻塞
        if sys.stdin.isatty() and prefer_binaries("自动打开页面", ["xdg-open"]):
            print("按回车键使用 xdg-open 打开页面", file=sys.stderr, end="", flush=True)
            try:
                input()
            except EOFError:
                pass
            else:
                try:
                    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                except OSError:
                    pass
        server_thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
