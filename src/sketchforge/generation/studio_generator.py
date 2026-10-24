"""Create a runnable, local-first web app project from a short product brief.

Generation order:
  1. AI generator (Nebius/OpenAI-compatible) — full-stack files tailored to the brief.
  2. Template generator (always available) — polished fallback when AI is offline.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Callable

from sketchforge.generation.app_specification import AppSpec, EntitySpec, FieldSpec, PageSpec
from sketchforge.generation.file_tree import materialise
from sketchforge.generation.project_planner import plan_html_css


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "new-app"


def generate_studio_project(
    prompt: str,
    target: Path,
    *,
    include_backend: bool = True,
    database: str = "sqlite",
    orm: str = "dataclass",
    api_target: str = "flask",
    authentication: bool = False,
    migrations: bool = False,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """Materialise frontend and optional configurable backend files under ``target``.

    Tries AI generation first; falls back to the template generator when the
    AI service is unavailable or returns unusable output.
    """
    brief = prompt.strip()
    if not brief:
        raise ValueError("Describe the app you want to build first.")

    # AI-generated output has a fixed Flask/SQLite contract; use the canonical
    # target renderers whenever the user selected another backend combination.
    if (database, orm, api_target, authentication, migrations) == ("sqlite", "dataclass", "flask", False, False):
        try:
            from sketchforge.generation.ai_generator import ai_generate_project
            ai_root = ai_generate_project(brief, target, include_backend=include_backend, progress=progress)
            if ai_root is not None and ai_root.is_dir():
                return ai_root
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("AI generation failed (%s); using templates.", exc)
            if progress:
                progress(f"AI generation unavailable ({exc}); generating from templates...")

    # --- Template fallback path ---
    if progress:
        progress("Generating project from templates...")

    name = " ".join(brief.split()[:3]).strip(".,:;!?—-").title() or "New App"
    pages = [
        PageSpec(
            name="home",
            title=name,
            route="/",
            description=brief,
            forms=[[FieldSpec("email", "Email address", "email", placeholder="you@example.com"),
                    FieldSpec("idea", "What are you working on?", "text", required=False,
                              placeholder="Share a few details…")]],
        ),
        PageSpec(name="projects", title="Your workspace", route="/projects",
                 description="A calm place to keep your work moving."),
    ]
    fields = [FieldSpec("email", "Email address", "email"),
              FieldSpec("idea", "Idea", "text", required=False)]
    spec = AppSpec(
        name=name,
        description=brief,
        pages=pages,
        entities=[EntitySpec("Submission", fields)] if include_backend else [],
        tech_frontend="html-css-js",
        tech_backend="python-sqlite" if include_backend else "none",
        database=database,
        orm=orm,
        api_target=api_target,
        authentication=authentication,
        migrations=migrations,
        acceptance_criteria=["Responsive pages render locally", "Forms validate and save submissions"]
    )
    root = target.resolve() / _slug(name)
    materialise(plan_html_css(spec), root)

    if include_backend:
        from sketchforge.generation.frontend.project_export import render_file
        # Reuse the canonical backend plan to keep Studio and planner generation aligned.
        from sketchforge.generation.project_planner import plan_react_ts
        canonical = plan_react_ts(spec)
        backend_files = [f for f in canonical.files if f.generator.startswith("backend_")]
        for planned in backend_files:
            path = planned.relative_path
            content = render_file(planned, canonical)
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content or "", encoding="utf-8")
    _write_frontend(root, spec)
    if include_backend and orm != "prisma":
        from sketchforge.generation.backend.schema_generator import _requirements
        (root / "requirements.txt").write_text(_requirements(spec), encoding="utf-8")
    backend_notes = (
        f"- `backend/prisma/schema.prisma`: Prisma schema; run `cd backend && npm install && npm run db:migrate`.\n"
        if include_backend and orm == "prisma" else
        f"- `backend/`: {database} schema, generated models/CRUD, {api_target} API, and optional auth.\n"
        f"- Install API dependencies with `python -m pip install -r requirements.txt`.\n"
        f"- Start Flask with `python -m backend.api`; start FastAPI/GraphQL with `uvicorn backend.api:app`.\n"
        f"- Set `DATABASE_URL` for PostgreSQL/MySQL. Set `AUTH_SECRET` for authentication. "
        f"Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to enable Google OAuth2."
        f"{' Apply schema changes with `alembic upgrade head`.' if migrations else ''}"
        if include_backend else "- Backend generation was not selected."
    )
    backend_start = (
        "Backend generation was not selected."
        if not include_backend else
        "Run `cd backend && npm install && npm run db:migrate` for the Prisma database client."
        if orm == "prisma" else
        "Run `uvicorn backend.api:app` for FastAPI/GraphQL, or `python -m backend.api` for Flask."
    )
    (root / "README.md").write_text(f"""# {name}

Responsive HTML, CSS, and JavaScript generated by SketchForge Studio.

## Frontend

Open `index.html` directly, or run a local static server from this directory:

```bash
python -m http.server 8000
```

Then visit `http://localhost:8000`.

## Backend API

{backend_start}

When generated from within SketchForge Studio, supported API backends start automatically for preview.

## Project files

- `home.html`, `projects.html`: linked app screens.
- `css/style.css`: responsive design system and page styles.
- `js/home.js`: form submission that POSTs to /api/submissions.
- `js/projects.js`: fetches and renders submissions from /api/submissions.
{"- Install backend dependencies with `python -m pip install -r requirements.txt`." if include_backend else ""}
{backend_notes}
""", encoding="utf-8")
    return root


def _write_frontend(root: Path, spec: AppSpec) -> None:
    """Give generated pages a polished, responsive surface with working navigation/forms."""
    for page in spec.pages:
        slug = page.name.lower()
        safe_name = escape(spec.name)
        safe_title = escape(page.title)
        safe_description = escape(page.description)
        html_path = root / f"{slug}.html"
        nav = "".join(
            f'<a href="{other.name.lower()}.html">{escape(other.title) if other.name != page.name else "Overview"}</a>'
            for other in spec.pages
        )
        form = """
        <form id="idea-form">
          <label>Email address<input name="email" type="email" placeholder="you@example.com" required></label>
          <label>Your idea<textarea name="idea" rows="3" placeholder="Share a few details…"></textarea></label>
          <button class="primary" type="submit">Create my workspace <span>↗</span></button>
          <p class="form-note" id="form-note">No account needed to explore your idea.</p>
        </form>
        """ if page.name == "home" else ""
        suggestions = (
            '<div class="ideas"><span class="idea-label">NEED A PLACE TO START?</span>'
            '<button type="button" class="idea-chip" data-idea="A thoughtful client portal for my small studio">A home for my client work <b>↗</b></button>'
            '<button type="button" class="idea-chip" data-idea="A simple habit tracker that feels good to use">A tiny habit tracker <b>↗</b></button>'
            '<button type="button" class="idea-chip" data-idea="A modern dashboard for my team projects">A calmer team dashboard <b>↗</b></button></div>'
            if page.name == "home" else
            '<div class="ideas"><a class="idea-chip" href="home.html">Start another idea <b>↗</b></a></div>'
        )
        html_path.write_text(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{safe_description}"><title>{safe_title} · {safe_name}</title><link rel="stylesheet" href="css/style.css"></head>
<body><header class="top"><a class="brand" href="home.html"><span class="brand-mark">s</span>{safe_name}</a><nav>{nav}</nav><button class="avatar" aria-label="Account">A</button></header>
<main><div class="eyebrow"><span class="spark">✳</span> YOUR NEXT IDEA, IN MOTION</div>
<section class="hero"><div class="hero-copy"><p class="kicker">A little more room to imagine</p><h1>{safe_title}<br><em>starts right here.</em></h1>
<p class="lede">{safe_description}</p><div class="proof"><span class="avatars"><i>A</i><i>M</i><i>J</i></span><span>Made for the way you think.</span><span class="proof-dot">·</span><span>Ready when you are.</span></div></div>
<aside class="welcome-card"><div class="card-top"><span class="card-icon">✳</span><span class="live-pill"><i></i> YOUR CANVAS</span></div><div class="orb orb-one"></div><div class="orb orb-two"></div><div class="card-art"><div class="art-window"><div class="art-nav"><b></b><span></span><span></span><span></span></div><div class="art-lines"><i></i><i></i><i></i></div><div class="art-blocks"><b></b><b></b><b></b></div></div><span class="float-chip">✦ &nbsp; good ideas live here</span></div><div class="card-foot"><span>BUILT AROUND YOUR IDEA</span><span>01 — 02</span></div></aside></section>
<section class="work"><div class="work-heading"><div><span class="kicker">THE FIRST STEP IS EASY</span><h2>What are we making?</h2></div><span class="counter">01 <i>/</i> 02</span></div>
<div class="builder"><div class="builder-head"><div class="builder-label"><span class="status-dot"></span><b>Tell us a little about it</b><span class="muted">· takes one sentence</span></div><span class="private">⌁ &nbsp; Private workspace</span></div>
{form if page.name == "home" else '<p class="lede">Your project pages, ready to explore.</p>'}
{suggestions}</div></section>
<footer><span>✳ &nbsp;SketchForge Studio</span><span>Made to move at the speed of your ideas&nbsp; ↗</span></footer></main><script src="js/{slug}.js"></script></body></html>''', encoding="utf-8")
        (root / "js" / f"{slug}.js").write_text(
            _home_js() if slug == "home" else _projects_js(),
            encoding="utf-8",
        )
    (root / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=home.html">'  # noqa: E501
        '<title>Opening app\u2026</title><a href="home.html">Open the app</a>',
        encoding="utf-8",
    )
    (root / "css" / "style.css").write_text(_studio_css(), encoding="utf-8")


def _home_js() -> str:
    return """\
// home.js — generated by SketchForge Studio
// Submits forms to the backend API; falls back to localStorage when offline.

document.querySelectorAll('[data-idea]').forEach(button =>
  button.addEventListener('click', () => {
    const field = document.querySelector('[name="idea"]');
    if (field) { field.value = button.dataset.idea; field.focus(); }
  })
);

const form = document.querySelector('#idea-form');
if (form) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    const note = document.querySelector('#form-note');
    const btn  = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = 'Saving…';
    try {
      const resp = await fetch('/api/submissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      note.textContent = 'Your workspace is ready — saved to the backend database.';
      note.classList.add('success');
      btn.textContent = 'Saved to your workspace ✓';
    } catch (err) {
      // Offline / no backend — save locally
      const saved = JSON.parse(localStorage.getItem('sketchforge-submissions') || '[]');
      saved.push({ ...data, createdAt: new Date().toISOString() });
      localStorage.setItem('sketchforge-submissions', JSON.stringify(saved));
      note.textContent = 'Saved locally (backend not reachable).';
      note.classList.add('success');
      btn.textContent = 'Saved locally ✓';
    }
  });
}
"""


def _projects_js() -> str:
    return """\
// projects.js — generated by SketchForge Studio
// Fetches submissions from the backend API and renders them.

async function loadSubmissions() {
  const list = document.querySelector('#submissions-list');
  if (!list) return;
  try {
    const resp = await fetch('/api/submissions');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const items = await resp.json();
    if (!items.length) {
      list.innerHTML = '<li class="empty-row">No submissions yet — use the home page to add one.</li>';
      return;
    }
    list.innerHTML = items.map(s => `
      <li class="submission-card">
        <span class="sub-email">${escHtml(s.email || '')}</span>
        <span class="sub-idea">${escHtml(s.idea || '—')}</span>
        <span class="sub-date">${new Date(s.created_at || s.createdAt || '').toLocaleString()}</span>
        <button class="delete-btn" data-id="${s.id}">✕</button>
      </li>`).join('');
    list.querySelectorAll('.delete-btn').forEach(btn =>
      btn.addEventListener('click', () => deleteSubmission(btn.dataset.id))
    );
  } catch {
    // Fall back to localStorage
    const saved = JSON.parse(localStorage.getItem('sketchforge-submissions') || '[]');
    if (!saved.length) {
      list.innerHTML = '<li class="empty-row">No submissions yet.</li>';
      return;
    }
    list.innerHTML = saved.map((s, i) => `
      <li class="submission-card">
        <span class="sub-email">${escHtml(s.email || '')}</span>
        <span class="sub-idea">${escHtml(s.idea || '—')}</span>
        <span class="sub-date">${new Date(s.createdAt || '').toLocaleString()}</span>
        <button class="delete-btn" data-idx="${i}">✕</button>
      </li>`).join('');
    list.querySelectorAll('.delete-btn').forEach(btn =>
      btn.addEventListener('click', () => {
        saved.splice(parseInt(btn.dataset.idx), 1);
        localStorage.setItem('sketchforge-submissions', JSON.stringify(saved));
        loadSubmissions();
      })
    );
  }
}

async function deleteSubmission(id) {
  try {
    await fetch(`/api/submissions/${id}`, { method: 'DELETE' });
    loadSubmissions();
  } catch { /* local storage handled in loadSubmissions fallback */ }
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

loadSubmissions();
"""


def _write_backend_api(root: Path, spec: AppSpec) -> None:
    """Write a Flask CRUD REST API to backend/api.py in the generated project."""
    from sketchforge.generation.backend.schema_generator import _snake
    entity = spec.entities[0] if spec.entities else None
    table = _snake(entity.name) if entity else "submission"
    fields = [f.name for f in entity.fields] if entity else ["email", "idea"]
    col_defs = ", ".join(f"{n} TEXT" for n in fields)
    insert_cols = ", ".join(fields)
    insert_placeholders = ", ".join("?" for _ in fields)
    insert_values = ", ".join(f"data.get('{n}', '')" for n in fields)

    api_py = f'''\
"""Flask CRUD REST API — generated by SketchForge Studio."""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request

app = Flask(__name__)
DB_PATH = Path(__file__).parent.parent / "data" / "{_snake(spec.name)}.db"

# ---------------------------------------------------------------------------
# Security: restricted CORS + ephemeral session-token gate
# ---------------------------------------------------------------------------
# CORS_ORIGIN is injected at startup by SketchForge Studio and set to the
# exact iframe origin (e.g. "http://127.0.0.1:PORT").  Wildcard (*) is only
# used when the env-var is absent so a bare `python backend/api.py` still
# works during manual development.
_ALLOWED_ORIGIN: str = os.environ.get("CORS_ORIGIN", "null")

# STUDIO_TOKEN is an ephemeral secret generated per preview session.  Every
# /api/ request must supply it in the X-Studio-Token header; requests without
# the token receive 401 before any application logic runs.
_STUDIO_TOKEN: str | None = os.environ.get("STUDIO_TOKEN") or None


@app.before_request
def _require_token():
    """Reject /api/* requests that do not carry the correct session token."""
    if not request.path.startswith("/api/"):
        return  # health / static routes pass through
    if request.method == "OPTIONS":
        return  # CORS pre-flight must not be gated
    if _STUDIO_TOKEN is None:
        return  # token gate disabled (e.g. running outside Studio preview)
    supplied = request.headers.get("X-Studio-Token", "")
    if not supplied or supplied != _STUDIO_TOKEN:
        return jsonify(error="unauthorized"), 401


def _cors(response):
    """Attach restricted CORS headers to every response."""
    # Only reflect the exact allowed origin, never a wildcard.
    if _ALLOWED_ORIGIN and _ALLOWED_ORIGIN != "null":
        response.headers["Access-Control-Allow-Origin"] = _ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Studio-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Vary"] = "Origin"
    return response


app.after_request(_cors)


@app.route("/api/<path:path>", methods=["OPTIONS"])
def _preflight(path):
    return app.make_default_options_response()


def _db() -> sqlite3.Connection:
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS {table} "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs}, "
            "created_at TEXT DEFAULT (datetime('now')))"
        )
        conn.commit()
        g.db = conn
    return g.db


@app.teardown_appcontext
def _close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.route("/api/submissions", methods=["GET"])
def list_submissions():
    rows = _db().execute(
        "SELECT * FROM {table} ORDER BY id DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/submissions", methods=["POST"])
def create_submission():
    data = request.get_json(force=True) or {{}}
    db = _db()
    cur = db.execute(
        "INSERT INTO {table} ({insert_cols}) VALUES ({insert_placeholders})",
        [{insert_values}],
    )
    db.commit()
    row = db.execute("SELECT * FROM {table} WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/submissions/<int:sub_id>", methods=["GET"])
def get_submission(sub_id: int):
    row = _db().execute("SELECT * FROM {table} WHERE id = ?", (sub_id,)).fetchone()
    if not row:
        return jsonify({{"error": "not found"}}), 404
    return jsonify(dict(row))


@app.route("/api/submissions/<int:sub_id>", methods=["PUT"])
def update_submission(sub_id: int):
    data = request.get_json(force=True) or {{}}
    db = _db()
    sets = ", ".join(f"{{k}} = ?" for k in data if k != "id")
    vals = [v for k, v in data.items() if k != "id"] + [sub_id]
    if not sets:
        return jsonify({{"error": "nothing to update"}}), 400
    db.execute(f"UPDATE {table} SET {{sets}} WHERE id = ?", vals)
    db.commit()
    row = db.execute("SELECT * FROM {table} WHERE id = ?", (sub_id,)).fetchone()
    return jsonify(dict(row)) if row else (jsonify({{"error": "not found"}}), 404)


@app.route("/api/submissions/<int:sub_id>", methods=["DELETE"])
def delete_submission(sub_id: int):
    db = _db()
    cur = db.execute("DELETE FROM {table} WHERE id = ?", (sub_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({{"error": "not found"}}), 404
    return "", 204


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    print(f"SketchForge API running on http://{{args.host}}:{{args.port}}")
    app.run(host=args.host, port=args.port, debug=False)
'''
    # Substitute template variables that use single-brace format
    api_py = api_py.replace("{table}", table).replace("{col_defs}", col_defs) \
                   .replace("{insert_cols}", insert_cols) \
                   .replace("{insert_placeholders}", insert_placeholders) \
                   .replace("{insert_values}", insert_values)
    dest = root / "backend" / "api.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(api_py, encoding="utf-8")
    # Ensure data directory exists
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / ".gitkeep").write_text("", encoding="utf-8")


def _studio_css() -> str:
    return ''':root{font-family:'Segoe UI',sans-serif;color:#f1f0f5;background:#111116;font-synthesis:none;text-rendering:optimizeLegibility}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse 65% 38% at 80% 3%,#29243a 0%,transparent 72%),radial-gradient(ellipse 48% 32% at 4% 78%,#191b28 0%,transparent 70%),#111116}.top{height:72px;border-bottom:1px solid #ffffff12;display:flex;align-items:center;padding:0 5.5%;gap:40px}.brand{font:700 17px 'Segoe UI',sans-serif;letter-spacing:-.6px;color:#f6f4fa;text-decoration:none;display:flex;align-items:center;gap:10px}.brand-mark{width:27px;height:27px;border-radius:9px;background:#d9ff5f;color:#17180f;display:grid;place-items:center;font-size:18px}.top nav{display:flex;gap:28px;margin:auto;font-size:12px;color:#aaa7b3}.top nav a{color:inherit;text-decoration:none}.avatar{border:1px solid #ffffff25;background:#282730;color:white;border-radius:50%;width:32px;height:32px}.top button,button{font:inherit}.top .avatar{cursor:pointer}main{max-width:1080px;margin:auto;padding:42px 54px 0}.eyebrow,.kicker,.idea-label{font-size:10px;letter-spacing:1.45px;font-weight:700;color:#aba7b7}.eyebrow{display:flex;align-items:center;gap:8px}.spark{color:#d9ff5f;font-size:14px}.hero{display:grid;grid-template-columns:1.04fr .96fr;gap:54px;align-items:center;padding:28px 0 43px}.hero-copy{padding:18px 0}.kicker{color:#c5c2ce;letter-spacing:.35px}.hero h1{font:600 clamp(42px,5.1vw,66px)/1.07 'Segoe UI',sans-serif;letter-spacing:-3.5px;margin:14px 0 18px}.hero h1 em{font-weight:400;color:#d9ff5f;font-style:normal}.lede{font-size:15px;line-height:1.72;color:#b4b1bf;max-width:440px}.proof{display:flex;align-items:center;gap:9px;margin-top:25px;color:#9b98a4;font-size:10px}.avatars{display:flex;padding-left:3px}.avatars i{font-style:normal;width:22px;height:22px;border:2px solid #111116;margin-left:-4px;border-radius:50%;display:grid;place-items:center;background:#33344c;color:#d9ff5f;font-size:9px}.avatars i:nth-child(2){background:#514050;color:#f6ceaf}.avatars i:nth-child(3){background:#304148;color:#b1e9df}.proof-dot{color:#d9ff5f}.welcome-card{height:286px;position:relative;border:1px solid #ffffff1a;border-radius:20px;background:linear-gradient(135deg,#22212c,#181820 67%);overflow:hidden;padding:18px 21px;box-shadow:0 28px 80px #0005}.card-top,.card-foot{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:1}.card-icon{width:27px;height:27px;border-radius:9px;background:#d9ff5f;color:#17180f;display:grid;place-items:center}.live-pill{font-size:8px;color:#acabb5;letter-spacing:1px}.live-pill i,.status-dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#d9ff5f;margin-right:6px;box-shadow:0 0 10px #d9ff5f}.orb{position:absolute;border-radius:50%;filter:blur(35px);opacity:.7}.orb-one{background:#7760d4;width:130px;height:130px;top:105px;left:50px}.orb-two{background:#92b544;width:90px;height:90px;right:40px;top:115px;opacity:.35}.card-art{position:absolute;inset:54px 32px 39px;display:grid;place-items:center}.art-window{width:76%;height:154px;border-radius:11px;background:#111218ed;border:1px solid #ffffff28;padding:13px;box-shadow:0 18px 45px #0007;transform:rotate(-4deg)}.art-nav{display:flex;gap:8px;align-items:center;border-bottom:1px solid #ffffff17;padding-bottom:10px}.art-nav b{width:12px;height:12px;border-radius:4px;background:#d9ff5f}.art-nav span{width:27px;height:4px;border-radius:4px;background:#4d4a58}.art-lines{padding:14px 4px;display:grid;gap:7px}.art-lines i{height:5px;border-radius:4px;background:#bab3cd;width:60%}.art-lines i:nth-child(2){width:43%;background:#d9ff5f}.art-lines i:nth-child(3){width:53%;background:#575364}.art-blocks{display:flex;gap:7px}.art-blocks b{height:30px;flex:1;border-radius:5px;background:#272632}.art-blocks b:first-child{background:#342e48}.art-blocks b:last-child{background:#303628}.float-chip{position:absolute;right:7px;bottom:12px;background:#d9ff5f;color:#17180f;padding:8px 12px;border-radius:8px;font-size:9px;font-weight:700;box-shadow:0 8px 20px #0006}.card-foot{position:absolute;bottom:17px;left:21px;right:21px;font-size:8px;letter-spacing:1px;color:#85828d}.work{border-top:1px solid #ffffff18;padding-top:29px}.work-heading{display:flex;justify-content:space-between;align-items:end;margin-bottom:16px}.work-heading h2{font:600 21px 'Segoe UI',sans-serif;letter-spacing:-.7px;margin:6px 0 0}.counter{font-size:10px;color:#a5a1af}.counter i{color:#d9ff5f;font-style:normal}.builder{border:1px solid #ffffff25;border-radius:16px;background:linear-gradient(125deg,#201f29,#19191f);padding:18px 20px 16px;box-shadow:0 16px 48px #0003}.builder-head,.builder-label{display:flex;align-items:center;gap:9px}.builder-head{justify-content:space-between;margin-bottom:12px}.builder-label{font-size:11px}.muted{color:#898693}.private{font-size:9px;color:#85818e}.builder form{display:grid;grid-template-columns:1fr 1.2fr auto;align-items:end;gap:12px}.builder label{display:grid;gap:7px;font-size:10px;color:#c8c5d0}.builder input,.builder textarea{font:12px 'Segoe UI',sans-serif;resize:vertical;color:#f2eff7;background:#15151a;border:1px solid #ffffff20;border-radius:9px;padding:11px 12px;outline:none;min-height:39px}.builder input:focus,.builder textarea:focus{border-color:#d9ff5f88}.primary{height:40px;border:0;background:#d9ff5f;color:#16170e;border-radius:9px;padding:0 16px;font-size:11px;font-weight:700;cursor:pointer;white-space:nowrap}.primary:hover{background:#e5ff90}.primary span{padding-left:8px}.form-note{grid-column:1/-1;margin:0;color:#888591;font-size:9px}.form-note.success{color:#d9ff5f}.ideas{display:flex;align-items:center;gap:7px;margin-top:16px;flex-wrap:wrap}.idea-label{font-size:8px;margin-right:2px}.idea-chip{border:1px solid #ffffff20;background:#ffffff07;color:#c4c1cd;border-radius:999px;padding:7px 10px;font-size:9px;cursor:pointer}.idea-chip:hover{border-color:#d9ff5f77;color:#e4ff98}.idea-chip b{padding-left:8px;color:#d9ff5f}footer{margin-top:34px;padding:14px 0 21px;border-top:1px solid #ffffff12;display:flex;justify-content:space-between;color:#777480;font-size:9px}footer span:first-child{color:#c6c3cd}.submission-card{list-style:none;display:grid;grid-template-columns:1fr 2fr 1fr auto;gap:10px;align-items:center;border-bottom:1px solid #ffffff12;padding:10px 0}.sub-email{color:#d9ff5f;font-size:11px}.sub-idea{font-size:11px;color:#c9c5d4}.sub-date{font-size:9px;color:#888590}.delete-btn{background:transparent;border:1px solid #ffffff20;color:#888;border-radius:6px;padding:4px 8px;cursor:pointer;font-size:10px}.delete-btn:hover{border-color:#ff6b6b;color:#ff6b6b}.empty-row{color:#777480;font-size:11px;padding:12px 0;list-style:none}@media(max-width:760px){main{padding:26px 22px 0}.top{padding:0 22px}.top nav{gap:12px}.top nav a:nth-child(n+3){display:none}.hero{grid-template-columns:1fr;gap:18px;padding:12px 0 28px}.welcome-card{height:220px}.art-window{height:120px}.builder form{grid-template-columns:1fr}.form-note{grid-column:auto}.builder-head{align-items:flex-start}.private{display:none}.hero h1{letter-spacing:-2px}footer span:last-child{display:none}.submission-card{grid-template-columns:1fr auto}}
'''


