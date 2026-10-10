"""Temporary same-origin reverse proxy for local Wave3 validation. Not part of product source."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.request

API = "http://127.0.0.1:8008"
WEB = "http://127.0.0.1:22785"

class H(BaseHTTPRequestHandler):
    def _proxy(self):
        target = API if self.path.startswith("/api") else WEB
        url = target + self.path
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(url, data=body, method=self.command)
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in {"host", "content-length", "transfer-encoding", "connection"}:
                continue
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in {"transfer-encoding", "connection", "content-encoding"}:
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            msg = str(e).encode("utf-8", "replace")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self): self._proxy()
    def do_POST(self): self._proxy()
    def do_PUT(self): self._proxy()
    def do_PATCH(self): self._proxy()
    def do_DELETE(self): self._proxy()
    def do_OPTIONS(self): self._proxy()
    def log_message(self, fmt, *args): pass

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 5173), H).serve_forever()
