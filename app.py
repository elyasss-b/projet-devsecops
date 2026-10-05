"""Notes : mini application Flask de prise de notes (stockage en memoire)."""

import itertools
import os

from flask import Flask, abort, jsonify, render_template, request

app = Flask(__name__)
app.config["APP_VERSION"] = os.environ.get("APP_VERSION", "dev")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

MAX_TITLE_LENGTH = 100

_notes = {}
_ids = itertools.count(1)


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/")
def index():
    return render_template(
        "index.html", notes=list(_notes.values()), version=app.config["APP_VERSION"]
    )


@app.get("/health")
def health():
    return jsonify(status="ok", version=app.config["APP_VERSION"])


@app.get("/api/notes")
def list_notes():
    return jsonify(list(_notes.values()))


@app.post("/api/notes")
def create_note():
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return jsonify(error="title est obligatoire"), 400
    if len(title) > MAX_TITLE_LENGTH:
        return jsonify(error=f"title limite a {MAX_TITLE_LENGTH} caracteres"), 400
    note_id = next(_ids)
    _notes[note_id] = {"id": note_id, "title": title.strip()}
    return jsonify(_notes[note_id]), 201


@app.get("/api/notes/<int:note_id>")
def get_note(note_id):
    if note_id not in _notes:
        abort(404)
    return jsonify(_notes[note_id])


@app.delete("/api/notes/<int:note_id>")
def delete_note(note_id):
    if _notes.pop(note_id, None) is None:
        abort(404)
    return "", 204
