from __future__ import annotations

import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import HOST, PORT, ROOT
from backend.controller import ControllerAgent


controller = ControllerAgent()
frontend = ROOT / "frontend"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.respond({"ok": True, "service": "because-of-you"})
        if path.startswith("/api/session/"):
            parts = path.strip("/").split("/")
            try:
                return self.respond(controller.report(parts[2]) if len(parts) == 4 and parts[3] == "report" else controller.view(controller.load(parts[2])))
            except KeyError:
                return self.respond({"error": "存档不存在"}, 404)
        self.static(path)

    def do_POST(self) -> None:
        path, body = urlparse(self.path).path, self.body()
        try:
            if path == "/api/session":
                return self.respond(controller.create_session(body.get("seed"), body.get("name"), body.get("preferences")))
            if path.startswith("/api/session/") and path.endswith("/act"):
                session_id = path.strip("/").split("/")[2]
                return self.respond(controller.act(session_id, body.get("action", "free"), body.get("free_text", ""), int(body.get("hesitation_ms", 0))))
        except (KeyError, ValueError) as error:
            return self.respond({"error": str(error)}, 400)
        self.respond({"error": "接口不存在"}, 404)

    def body(self) -> dict:
        try:
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return {}

    def respond(self, value: object, status: int = 200) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(raw)

    def static(self, path: str) -> None:
        target = (frontend / ("index.html" if path in {"", "/"} else path.lstrip("/"))).resolve()
        if frontend.resolve() not in target.parents or not target.is_file():
            target = frontend / "index.html"
        raw = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    print(f"Because of YOU: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
