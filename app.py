# -*- coding: utf-8 -*-
"""编程能力测试平台后端：注册/登录 + 题库 + 本地评测。"""
import os
import sqlite3

from flask import Flask, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from questions import LANG_MAP, LEVELS, QUESTIONS, find_question
from runner import run_code

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "codejudge.db")
SECRET_PATH = os.path.join(BASE, "secret.key")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["ENV"] = "production"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def _load_secret():
    if os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "rb") as f:
            return f.read()
    secret = os.urandom(24)
    with open(SECRET_PATH, "wb") as f:
        f.write(secret)
    return secret


app.secret_key = _load_secret()


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                code TEXT NOT NULL,
                passed INTEGER NOT NULL,
                output TEXT,
                submitted_at TEXT DEFAULT (datetime('now','localtime'))
            )"""
        )
        conn.commit()


def _norm(s):
    return "\n".join(line.rstrip() for line in s.rstrip("\n").splitlines())


# ------------------------------ 页面 ------------------------------
@app.route("/")
def index():
    return app.send_static_file("index.html")


# ------------------------------ 账号 ------------------------------
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not (3 <= len(username) <= 20):
        return jsonify({"error": "用户名长度需在 3~20 之间"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码长度至少 6 位"}), 400
    with _db() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "用户名已存在"}), 409
    session["user_id"] = conn.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchone()["id"]
    return jsonify({"ok": True, "username": username})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    with _db() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "用户名或密码错误"}), 401
    session["user_id"] = row["id"]
    return jsonify({"ok": True, "username": row["username"]})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def me():
    if "user_id" not in session:
        return jsonify({"user": None})
    with _db() as conn:
        row = conn.execute(
            "SELECT id, username, created_at FROM users WHERE id = ?",
            (session["user_id"],),
        ).fetchone()
    if row is None:
        session.clear()
        return jsonify({"user": None})
    return jsonify({"user": dict(row)})


# ------------------------------ 题库 ------------------------------
@app.route("/api/questions")
def list_questions():
    lang = request.args.get("lang", "")
    level = request.args.get("level", "")
    items = []
    for q in QUESTIONS:
        if lang and q["lang"] != lang:
            continue
        if level and q["level"] != level:
            continue
        items.append(
            {
                "id": q["id"],
                "lang": q["lang"],
                "level": q["level"],
                "title": q["title"],
            }
        )
    return jsonify({"levels": LEVELS, "items": items})


@app.route("/api/questions/<qid>")
def question_detail(qid):
    q = find_question(qid)
    if q is None:
        return jsonify({"error": "题目不存在"}), 404
    return jsonify(
        {
            "id": q["id"],
            "lang": q["lang"],
            "lang_name": LANG_MAP[q["lang"]]["name"],
            "level": q["level"],
            "level_name": LEVELS[q["level"]],
            "title": q["title"],
            "desc": q["desc"],
            "stdin": q.get("stdin", ""),
        }
    )


# ------------------------------ 评测 ------------------------------
@app.route("/api/judge", methods=["POST"])
def judge():
    if "user_id" not in session:
        return jsonify({"error": "请先登录"}), 401
    data = request.get_json(silent=True) or {}
    qid = data.get("question_id")
    code = data.get("code") or ""
    q = find_question(qid)
    if q is None:
        return jsonify({"error": "题目不存在"}), 404
    if not code.strip():
        return jsonify({"error": "代码不能为空"}), 400
    if len(code) > 20000:
        return jsonify({"error": "代码过长（上限 20000 字符）"}), 400

    result = run_code(q["lang"], code, q.get("stdin", ""))
    if not result["ok"]:
        with _db() as conn:
            conn.execute(
                "INSERT INTO submissions (user_id, question_id, code, passed, output) VALUES (?,?,?,?,?)",
                (session["user_id"], qid, code, 0, result["error"]),
            )
            conn.commit()
        return jsonify({"passed": False, "error": result["error"]})

    output = result["output"]
    passed = _norm(output) == _norm(q["expected"])
    with _db() as conn:
        conn.execute(
            "INSERT INTO submissions (user_id, question_id, code, passed, output) VALUES (?,?,?,?,?)",
            (session["user_id"], qid, code, 1 if passed else 0, output),
        )
        conn.commit()
    resp = {
        "passed": passed,
        "output": output,
        "expected": q["expected"] if not passed else None,
    }
    if passed:
        resp["explain"] = q["explain"]
    return jsonify(resp)


# ------------------------------ 进度 ------------------------------
@app.route("/api/progress")
def progress():
    if "user_id" not in session:
        return jsonify({"passed": {}, "stats": {}, "totals": {}})
    with _db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT question_id FROM submissions WHERE user_id = ? AND passed = 1",
            (session["user_id"],),
        ).fetchall()
    passed = {r["question_id"]: True for r in rows}
    stats = {"python": 0, "c": 0, "java": 0, "rust": 0, "cpp": 0}
    for q in QUESTIONS:
        if q["id"] in passed:
            stats[q["lang"]] += 1
    totals = {"python": 0, "c": 0, "java": 0, "rust": 0, "cpp": 0}
    for q in QUESTIONS:
        totals[q["lang"]] += 1
    return jsonify({"passed": passed, "stats": stats, "totals": totals})


_init_db()

if __name__ == "__main__":
    import logging, click, werkzeug.serving
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    werkzeug.serving._log = lambda *a, **k: None
    click.echo = lambda *a, **k: None
    click.secho = lambda *a, **k: None
    print("http://127.0.0.1:8000", flush=True)
    app.run(host="127.0.0.1", port=8000, debug=False)
