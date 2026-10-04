import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
IDENTITY = os.environ.get("BACKEND", "A")
PORT = int(os.environ.get("PORT", "3001"))
ETAG = '"team-cache-v1"'
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_HEAD(self):
        self.reply(True)
    def do_GET(self):
        self.reply(False)
    def reply(self, head):
        path = self.path.split("?", 1)[0]
        cached = path == "/cache"
        known = path in ("/", "/api/status", "/cache")
        payload = ({"message": "shared cache content v1"} if cached
        else {"backend": IDENTITY, "status": "ok"})
        if not known:
            payload = {"error": "not found"}
        body = json.dumps(payload).encode()
        unchanged = cached and self.headers.get("If-None-Match") == ETAG
        status = 304 if unchanged else (200 if known else 404)
        self.send_response(status)
        self.send_header("X-Backend", IDENTITY)
        self.send_header("Cache-Control", "public, max-age=60" if cached else "no-store")
        if cached:
            self.send_header("ETag", ETAG)
        if status != 304:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head and status != 304:
            self.wfile.write(body)


ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()