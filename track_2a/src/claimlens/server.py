"""Local prototype HTTP interface. The CLI is the submission entry point."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .booklets import require_text
from .corpus import find_proposal, load_corpus, public_config
from .engine import check_claim
from .library import BookletLibrary
from .models import ClaimLensError, ValidationError
from .runtime import model_status

STATIC = Path(__file__).parent / "static"
ASSETS = {"/": ("index.html", "text/html"), "/static/styles.css": ("styles.css", "text/css"), "/static/app.js": ("app.js", "text/javascript")}


def create_server(settings, host="127.0.0.1", port=8000, library=None):
    proposals = load_corpus()
    library = library if library is not None else BookletLibrary()
    inference_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Claims, credentials, and model replies are not logged.

        def valid_host(self):
            """A local server must not trust attacker-controlled DNS aliases."""
            try:
                authority = urlsplit("//" + self.headers.get("Host", ""))
                allowed = {"127.0.0.1", "localhost", "::1"}
                if host not in ("0.0.0.0", "::"):
                    allowed.add(host)
                return (authority.hostname in allowed and not authority.username and not authority.password
                        and not authority.path and not authority.query and not authority.fragment
                        and (authority.port is None or 1 <= authority.port <= 65535))
            except ValueError:
                return False

        def respond(self, status, body, content_type="application/json"):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type != "application/pdf" else ""))
            if content_type == "application/pdf":
                self.send_header("Content-Disposition", 'inline; filename="claimlens-booklet.pdf"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.valid_host():
                self.respond(403, {"error": "Use the configured local address to access ClaimLens."})
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/config":
                    config = public_config(settings, proposals)
                    config["documents"] = library.list_documents()
                    config["version"] = "0.2"
                    config["request_timeout_seconds"] = getattr(settings, "document_timeout", settings.timeout) + 10
                    self.respond(200, config)
                elif path == "/api/library":
                    self.respond(200, {"documents": library.list_documents()})
                elif path == "/api/model/status":
                    self.respond(200, model_status(settings))
                elif path.startswith("/api/booklets/") and path.endswith("/pdf"):
                    document_id = path[len("/api/booklets/"):-len("/pdf")]
                    self.respond(200, library.pdf_path(document_id).read_bytes(), "application/pdf")
                elif path == "/health":
                    self.respond(200, {"status": "ok", "version": "0.2"})
                elif path in ASSETS:
                    filename, mime = ASSETS[path]
                    self.respond(200, (STATIC / filename).read_bytes(), mime)
                else:
                    self.respond(404, {"error": "Not found."})
            except ClaimLensError as exc:
                self.respond(exc.status_code, {"error": str(exc)})
            except OSError:
                self.respond(500, {"error": "The requested local document could not be read."})

        def do_POST(self):
            if not self.valid_host():
                self.respond(403, {"error": "Use the configured local address to access ClaimLens."})
                return
            path = urlsplit(self.path).path
            if path not in ("/api/check", "/api/booklets/import", "/api/booklets/upload"):
                self.respond(404, {"error": "Not found."})
                return
            # Block another website from initiating billable local inference.
            origin = self.headers.get("Origin")
            if origin and (urlsplit(origin).netloc != self.headers.get("Host") or urlsplit(origin).scheme not in ("http", "https")):
                self.respond(403, {"error": "Cross-origin requests are not allowed."})
                return
            expected_type = "application/pdf" if path.endswith("/upload") else "application/json"
            if self.headers.get("Content-Type", "").split(";")[0] != expected_type:
                self.respond(415, {"error": "Use {}.".format(expected_type)})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = 25_000_000 if path.endswith("/upload") else 16000
                if not 0 < length <= maximum:
                    raise ValidationError("Request body must be between 1 and {} bytes.".format(maximum))
                if path.endswith("/upload"):
                    params = parse_qs(urlsplit(self.path).query)
                    metadata = {key: params.get(key, [""])[0] for key in ("language", "title", "vote")}
                    body = self.rfile.read(length)
                    if len(body) != length:
                        raise ValidationError("The PDF upload was incomplete.")
                    self.respond(201, {"document": library.import_pdf(body, **metadata)})
                    return
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValidationError("Request must be a JSON object.")
                if path.endswith("/import"):
                    self.respond(201, {"document": library.import_url(
                        request.get("url"), request.get("language"),
                        title=request.get("title", ""), vote=request.get("vote", ""))})
                    return
                if request.get("document_id"):
                    if request.get("proposal_id"):
                        raise ValidationError("Select one booklet or one walkthrough source.")
                    if request.get("mode") != "live":
                        raise ValidationError("Imported booklets require Live Apertus.")
                    vote = require_text(request.get("vote"), "Proposal name", 2000)
                    proposal = library.get_proposal(request["document_id"], vote=vote)
                else:
                    proposal = find_proposal(proposals, request.get("proposal_id"))
                if not inference_lock.acquire(blocking=False):
                    self.respond(409, {"error": "A claim check is already running. Wait for it to finish before submitting another."})
                    return
                try:
                    result = check_claim(proposal, request.get("claim"), request.get("model", settings.model),
                                         request.get("mode", "demo"), settings,
                                         claim_language=request.get("claim_language", "auto"))
                finally:
                    inference_lock.release()
                if proposal.get("warnings"):
                    result["warnings"] = list(dict.fromkeys(proposal["warnings"] + result["warnings"]))
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
