"""Local prototype HTTP interface. The CLI is the submission entry point."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .corpus import find_proposal, load_corpus, public_config
from .engine import check_claim
from .models import ClaimLensError, ValidationError

STATIC = Path(__file__).parent / "static"
ASSETS = {"/": ("index.html", "text/html"), "/static/styles.css": ("styles.css", "text/css"), "/static/app.js": ("app.js", "text/javascript")}


def create_server(settings, host="127.0.0.1", port=8000):
    proposals = load_corpus()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Claims, credentials, and model replies are not logged.

        def respond(self, status, body, content_type="application/json"):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/config":
                self.respond(200, public_config(settings, proposals))
            elif path == "/health":
                self.respond(200, {"status": "ok"})
            elif path in ASSETS:
                filename, mime = ASSETS[path]
                self.respond(200, (STATIC / filename).read_bytes(), mime)
            else:
                self.respond(404, {"error": "Not found."})

        def do_POST(self):
            if self.path != "/api/check":
                self.respond(404, {"error": "Not found."})
                return
            # Block another website from initiating billable local inference.
            origin = self.headers.get("Origin")
            if origin and (urlsplit(origin).netloc != self.headers.get("Host") or urlsplit(origin).scheme not in ("http", "https")):
                self.respond(403, {"error": "Cross-origin requests are not allowed."})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.respond(415, {"error": "Use application/json."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16000:
                    raise ValidationError("Request body must be between 1 and 16000 bytes.")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValidationError("Request must be a JSON object.")
                proposal = find_proposal(proposals, request.get("proposal_id"))
                result = check_claim(proposal, request.get("claim"), request.get("model", settings.model),
                                     request.get("mode", "demo"), settings,
                                     claim_language=request.get("claim_language", "auto"))
                self.respond(200, result)
            except ClaimLensError as exc:
                self.respond(exc.status_code, {"error": str(exc)})
            except (ValueError, UnicodeError):
                self.respond(400, {"error": "Request body is not valid UTF-8 JSON."})
            except Exception:
                self.respond(500, {"error": "The request could not be completed. Check the local configuration."})

    return ThreadingHTTPServer((host, port), Handler)


def serve(settings, host="127.0.0.1", port=8000):
    server = create_server(settings, host, port)
    print("ClaimLens is available at http://{}:{} (Ctrl+C to stop).".format(host, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
