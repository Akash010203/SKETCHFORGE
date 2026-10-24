"""Local browser studio for generating and previewing complete SketchForge apps."""

from __future__ import annotations

import json
import logging
import mimetypes
import io
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from sketchforge.generation.studio_generator import generate_studio_project
from sketchforge.utilities.paths import repo_root

log = logging.getLogger(__name__)
_JOBS: dict[str, dict] = {}
_PROJECTS: dict[str, Path] = {}
_PREVIEWS: dict[str, str] = {}
_PREVIEW_SERVERS: list[ThreadingHTTPServer] = []
_BACKENDS: list[object] = []
_LOCK = threading.Lock()
_WEB_ROOT = Path(__file__).with_name("web_studio")


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "SketchForgeStudio/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/studio"}:
            self._static(_WEB_ROOT / "index.html")
        elif parsed.path.startswith("/assets/"):
            name = Path(unquote(parsed.path.removeprefix("/assets/"))).name
            self._static(_WEB_ROOT / name)
        elif parsed.path == "/api/projects":
            with _LOCK:
                projects = [{"name": p.name, "slug": slug} for slug, p in _PROJECTS.items()]
            self._json(200, projects)
        elif parsed.path.startswith("/api/export/"):
            slug = unquote(parsed.path.removeprefix("/api/export/"))
            with _LOCK:
                root = _PROJECTS.get(slug)
            if root is None or not root.is_dir():
                self._json(404, {"error": "Project not found."})
                return
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for file in sorted(root.rglob("*")):
                    if file.is_file() and not any(part.startswith(".") for part in file.relative_to(root).parts):
                        bundle.write(file, file.relative_to(root).as_posix())
            payload = archive.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{root.name}.zip"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            with _LOCK:
                job = _JOBS.get(job_id)
            self._json(200 if job else 404, job or {"error": "Job not found"})
        elif parsed.path.startswith("/preview/"):
            self._serve_preview(parsed.path)
        elif parsed.path.startswith("/api/project-api/"):
            self._proxy_api("GET", slug=unquote(parsed.path.split("/", 3)[3]), api_path=parsed.query)
        elif parsed.path.startswith("/api/"):
            self._proxy_api("GET")
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/api/upload/"):
            slug = unquote(urlparse(self.path).path.rsplit("/", 1)[-1])
            with _LOCK:
                root = _PROJECTS.get(slug)
            if root is None:
                self._json(404, {"error": "Generate or open a project before adding an image."})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}.get(content_type)
            length = int(self.headers.get("Content-Length", 0))
            if extension is None or length < 1 or length > 10 * 1024 * 1024:
                self._json(400, {"error": "Choose a PNG, JPEG, WebP, or GIF image under 10 MB."})
                return
            data = self.rfile.read(length)
            if len(data) != length:
                self._json(400, {"error": "Image upload was incomplete."})
                return
            upload = root / "assets" / "uploads" / f"{uuid.uuid4().hex}{extension}"
            upload.parent.mkdir(parents=True, exist_ok=True)
            upload.write_bytes(data)
            self._json(201, {"url": f"/assets/uploads/{upload.name}"})
        elif self.path == "/api/generate" or self.path.startswith("/api/revise/"):
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                prompt = str(data.get("prompt", "")).strip()
                if not prompt:
                    self._json(400, {"error": "Describe the app you want to create."})
                    return
                job_id = uuid.uuid4().hex[:12]
                with _LOCK:
                    _JOBS[job_id] = {"status": "running", "progress": "Starting generation…"}
                if self.path.startswith("/api/revise/"):
                    slug = unquote(self.path.rsplit("/", 1)[-1])
                    threading.Thread(target=self._revise, args=(job_id, slug, prompt), daemon=True).start()
                else:
                    threading.Thread(target=self._generate, args=(job_id, prompt), daemon=True).start()
                self._json(202, {"id": job_id})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json(400, {"error": f"Invalid request: {exc}"})
        elif self.path.startswith("/api/"):
            self._proxy_api("POST")
        else:
            self.send_error(404)

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/api/"):
            self._proxy_api("DELETE")
        else:
            self.send_error(404)

    def _generate(self, job_id: str, prompt: str) -> None:
        def progress(message: str) -> None:
            with _LOCK:
                _JOBS[job_id]["progress"] = message

        try:
            root = generate_studio_project(
                prompt, repo_root() / "output" / "projects", progress=progress
            )
            slug = root.name
            progress("Starting preview server and SQLite API…")
            preview_url = _start_project_preview(slug, root)
            with _LOCK:
                _PROJECTS[slug] = root
                _PREVIEWS[slug] = preview_url
                _JOBS[job_id].update(status="complete", project={"name": root.name, "slug": slug,
                                                                    "preview_url": preview_url})
        except Exception as exc:  # noqa: BLE001
            log.exception("Web studio generation failed")
            with _LOCK:
                _JOBS[job_id].update(status="failed", error=str(exc))

    def _revise(self, job_id: str, slug: str, instruction: str) -> None:
        with _LOCK:
            root = _PROJECTS.get(slug)
        if root is None:
            with _LOCK:
                _JOBS[job_id].update(status="failed", error="Generated project is no longer available.")
            return

        def progress(message: str) -> None:
            with _LOCK:
                _JOBS[job_id]["progress"] = message

        try:
            from sketchforge.generation.ai_generator import ai_revise_project
            updated = ai_revise_project(root, instruction, progress=progress)
            if not updated:
                raise RuntimeError("AI revision did not produce updated files. Check model configuration.")
            with _LOCK:
                _JOBS[job_id].update(status="complete", project={"name": root.name, "slug": slug})
        except Exception as exc:  # noqa: BLE001
            log.exception("Web studio revision failed")
            with _LOCK:
                _JOBS[job_id].update(status="failed", error=str(exc))

    def _serve_preview(self, path: str) -> None:
        parts = path.split("/", 3)
        if len(parts) < 3:
            self.send_error(404)
            return
        slug = unquote(parts[2])
        relative = unquote(parts[3]) if len(parts) > 3 else "home.html"
        with _LOCK:
            root = _PROJECTS.get(slug)
        if root is None:
            self.send_error(404)
            return
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            self.send_error(404)
            return
        self._static(target)

    def _proxy_api(self, method: str, *, slug: str | None = None, api_path: str | None = None) -> None:
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        if not slug:
            ref = urlparse(self.headers.get("Referer", "")).path.split("/")
            slug = unquote(ref[2]) if len(ref) > 2 and ref[1] == "preview" else ""
        with _LOCK:
            root = _PROJECTS.get(slug)
        if root is None:
            self._json(503, {"error": "No active generated project is associated with this request."})
            return
        # Generated projects use a local Flask API on a per-project port. Start it lazily.
        servers = getattr(self.server, "backend_servers", {})
        backend = servers.get(slug)
        if backend is None:
            try:
                from sketchforge.generation.backend_server import BackendServer
                backend = BackendServer()
                port = backend.start(root)
                if port is None:
                    self._json(503, {"error": "The generated backend could not start."})
                    return
                self.server.backend_servers[slug] = backend
            except Exception as exc:  # noqa: BLE001
                self._json(503, {"error": str(exc)})
                return
        suffix = api_path or self.path
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))) if method in {"POST", "PUT", "PATCH"} else None
        request = Request(f"http://127.0.0.1:{backend.port}{suffix}", data=body, method=method,
                          headers={
                              "Content-Type": self.headers.get("Content-Type", "application/json"),
                              "X-Studio-Token": backend.session_token or "",
                          })
        try:
            with urlopen(request, timeout=10) as response:
                payload, status = response.read(), response.status
        except HTTPError as exc:
            payload, status = exc.read(), exc.code
        except URLError as exc:
            self._json(502, {"error": f"Backend unavailable: {exc.reason}"})
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _static(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, value: object) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)


def serve_studio(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve the browser studio until interrupted."""
    server = StudioServer((host, port), StudioHandler)
    server.backend_servers = {}
    print(f"SketchForge Studio is available at http://{host}:{server.server_port}/studio", flush=True)
    try:
        server.serve_forever()
    finally:
        for backend in server.backend_servers.values():
            backend.stop()
        for backend in _BACKENDS:
            backend.stop()
        for preview_server in _PREVIEW_SERVERS:
            preview_server.shutdown()
            preview_server.server_close()
        server.server_close()


def _start_project_preview(slug: str, root: Path) -> str:
    """Serve one project on its own loopback origin and proxy its /api calls."""
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    from sketchforge.generation.backend_server import BackendServer

    backend = BackendServer()
    backend_port = backend.start(root)
    _BACKENDS.append(backend)

    class ProjectHandler(BaseHTTPRequestHandler):
        def _handle(self) -> None:
            path = urlparse(self.path).path
            if path == "/__sketchforge/save" and self.command == "POST":
                relative = unquote(pathlib_path_from_referer(self.headers.get("Referer", "")))
                target = (root / relative).resolve()
                if target.parent != root.resolve() or target.name not in {"home.html", "projects.html"}:
                    self.send_error(400)
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if length > 2 * 1024 * 1024:
                        raise ValueError("document too large")
                    data = json.loads(self.rfile.read(length))
                    html = data.get("html", "")
                    if not isinstance(html, str) or "<html" not in html.lower():
                        raise ValueError("invalid document")
                    target.write_text(html, encoding="utf-8")
                except (ValueError, json.JSONDecodeError) as exc:
                    self.send_error(400, str(exc))
                    return
                self.send_response(204)
                self.end_headers()
                return
            if path.startswith("/api/"):
                if backend_port is None:
                    payload = json.dumps({"error": "Generated backend did not start. Install project requirements."}).encode()
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))) if self.command in {"POST", "PUT", "PATCH"} else None
                req = Request(f"http://127.0.0.1:{backend_port}{self.path}", data=body, method=self.command,
                              headers={
                                  "Content-Type": self.headers.get("Content-Type", "application/json"),
                                  "X-Studio-Token": backend.session_token or "",
                              })
                try:
                    with urlopen(req, timeout=10) as resp:
                        payload, status = resp.read(), resp.status
                except HTTPError as exc:
                    payload, status = exc.read(), exc.code
                except URLError as exc:
                    payload, status = json.dumps({"error": str(exc.reason)}).encode(), 502
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if payload:
                    self.wfile.write(payload)
                return
            relative = unquote(urlparse(self.path).path).lstrip("/") or "home.html"
            target = (root / relative).resolve()
            if not target.is_relative_to(root.resolve()) or not target.is_file():
                self.send_error(404)
                return
            payload = target.read_bytes()
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix.lower() == ".html":
                monitor = (b"<script data-sketchforge-editor>(function(){function report(m,l){parent.postMessage({type:'sketchforge-error',message:String(m),line:l||'?'},'*')}"
                           b"addEventListener('error',e=>report(e.message,e.lineno));addEventListener('unhandledrejection',e=>report(e.reason));"
                           b"['dragenter','dragover'].forEach(t=>addEventListener(t,e=>{if(e.dataTransfer?.types.includes('Files')){e.preventDefault();e.dataTransfer.dropEffect='copy'}}));addEventListener('drop',e=>{if(e.dataTransfer?.types.includes('Files')){e.preventDefault();[...e.dataTransfer.files].filter(f=>f.type.startsWith('image/')).forEach(file=>parent.postMessage({type:'sf-file-drop',file},'*'))}});"
                           b"let f=window.fetch.bind(window);window.fetch=(...a)=>f(...a).then(r=>{if(!r.ok)report('HTTP '+r.status+' '+a[0],'API');return r});"
                           b"function save(){let d=document.documentElement.cloneNode(true);d.querySelectorAll('[data-sketchforge-editor]').forEach(x=>x.remove());fetch('/__sketchforge/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({html:'<!doctype html>'+d.outerHTML})}).then(r=>{if(!r.ok)throw Error();parent.postMessage({type:'sf-edit-saved'},'*')}).catch(()=>parent.postMessage({type:'sf-edit-error'},'*'))}"
                           b"let active=null;document.addEventListener('click',e=>{if(!window.sfEditMode)return;if(e.target.closest('[data-sketchforge-editor]'))return;e.preventDefault();e.stopPropagation();if(active)active.style.outline='';active=e.target;active.style.outline='2px solid #7c65e8';parent.postMessage({type:'sf-element-selected',text:active.innerText||active.alt||active.tagName},'*')},true);"
                           b"document.addEventListener('dblclick',e=>{if(!window.sfEditMode||!active)return;e.preventDefault();active.contentEditable='true';active.focus()});document.addEventListener('focusout',e=>{if(e.target.contentEditable==='true'){e.target.contentEditable='false';e.target.style.outline='';active=null;save()}},true);"
                           b"addEventListener('message',e=>{if(e.source!==parent)return;if(e.data?.type==='sf-snapshot'){parent.postMessage({type:'sf-state',state:{url:location.href,scrollX,scrollY,fields:[...document.querySelectorAll('input,textarea,select')].map((x,i)=>({i,value:x.value,checked:x.checked}))}},'*')}"
                           b"if(e.data?.type==='sf-edit-mode'){window.sfEditMode=!!e.data.enabled;document.body.style.cursor=window.sfEditMode?'crosshair':'';parent.postMessage({type:'sf-edit-mode-ready'},'*')}"
                           b"if(e.data?.type==='sf-insert-image'){let img=document.createElement('img');img.src=e.data.url;img.alt='Uploaded image';img.style.cssText='max-width:320px;height:auto;display:block;margin:16px;border-radius:8px';if(active&&active.parentElement)active.insertAdjacentElement('afterend',img);else(document.querySelector('main')||document.body).appendChild(img);active=img;save()}"
                           b"if(e.data?.type==='sf-add-text'){let el=document.createElement('h2');el.textContent='Add your text';el.contentEditable='true';el.style.cssText='padding:12px;border:1px dashed #7c65e8;min-height:44px';(document.querySelector('main')||document.body).appendChild(el);el.focus();active=el;el.addEventListener('blur',()=>{el.contentEditable='false';el.style.border='';save()},{once:true})}"
                           b"if(e.data?.type==='sf-restore'){let s=e.data.state||{};(s.fields||[]).forEach(x=>{let el=document.querySelectorAll('input,textarea,select')[x.i];if(el){el.value=x.value;el.checked=x.checked}});scrollTo(s.scrollX||0,s.scrollY||0)}})})()</script>")
                payload = payload.replace(b"</head>", monitor + b"</head>", 1)
            self.send_response(200)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"} else ""))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_DELETE = _handle
        do_OPTIONS = _handle

        def log_message(self, fmt: str, *args) -> None:
            log.info("[preview %s] %s", slug, fmt % args)

    preview_server = ThreadingHTTPServer(("127.0.0.1", 0), ProjectHandler)
    preview_server.daemon_threads = True
    threading.Thread(target=preview_server.serve_forever, daemon=True, name=f"sketchforge-preview-{slug}").start()
    _PREVIEW_SERVERS.append(preview_server)
    return f"http://127.0.0.1:{preview_server.server_port}/home.html"


def pathlib_path_from_referer(referer: str) -> str:
    """Return the generated HTML page name for the editor save request."""
    from urllib.parse import urlparse
    name = Path(urlparse(referer).path).name
    return name if name in {"home.html", "projects.html"} else ""
