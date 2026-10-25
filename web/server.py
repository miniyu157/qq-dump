"""QQ DUMP WebUI：本地 HTTP 服务、静态页面与 JSON 接口。"""

import errno
import json
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from api import load_friends, load_owner
from lib.ansi import _bold, _reset, _tty
from lib.utils import good_log
from service.avatars import avatar, prepare_cache

HOST = "127.0.0.1"
PORT = 40080

STATIC = (Path(__file__).resolve().parent / "static").resolve()
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


class Server(ThreadingHTTPServer):
    """客户端提前断开属于常态，不作为服务端异常记录"""

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
            if url.path != "/api/jobs":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "请求体不是合法 JSON"})
                return
            if not isinstance(body.get("uids"), list) or not all(isinstance(uid, str) for uid in body["uids"]):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "uids 必须是字符串数组"})
                return
            # 下一个 API 尚未实现，先固定返回 501
            self._json(HTTPStatus.NOT_IMPLEMENTED, {"error": f"操作尚未实现: {body.get('op')}"})

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

    return Server((HOST, PORT), Handler)


def serve(profile_db: str, nt_db: str | None = None) -> None:
    """启动 WebUI 并阻塞到 Ctrl+C"""
    try:
        server = create_server(profile_db, nt_db)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            raise SystemExit(f"端口 {PORT} 已被占用") from exc
        raise

    host, port = server.server_address
    url = f"http://{host}:{port}/"
    if _tty:
        print("\033[2J\033[H", end="", flush=True)
    print(f"{_bold}QQ DUMP WebUI{_reset}")
    good_log(url)
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
