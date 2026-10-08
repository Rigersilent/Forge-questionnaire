# -*- coding: utf-8 -*-
"""
FORGE — serveur web du questionnaire "Capital récupération"
============================================================

Un seul fichier qui fait tout :
  • sert le questionnaire public               ->  GET  /
  • reçoit et enregistre chaque soumission     ->  POST /api/submit   (SQLite)
  • interface privée équipe (login mdp)        ->  GET  /admin        (tableau, filtres)
  • détail d'une soumission                    ->  GET  /admin/<id>
  • export CSV de la base                       ->  GET  /admin/export.csv
  • statistiques simples (personas, moyennes)  ->  intégré au tableau de bord

Lancement local :
    pip install flask
    export FORGE_ADMIN_PASSWORD="choisis-un-mot-de-passe"
    export FORGE_SECRET_KEY="une-longue-chaine-aleatoire"
    python app.py                 # http://127.0.0.1:8000

Déploiement : voir DEPLOIEMENT.md (Render / Railway / VPS).
Le questionnaire HTML (forge-quiz-v8.html) doit être dans le même dossier.

RGPD : données personnelles (prénom, email) + données de santé déclaratives.
  - Hébergez en UE, en HTTPS.
  - 'consentementRecherche' distingue l'usage CRM (toujours) de la publication
    scientifique (seulement si True). L'export marque cette colonne.
  - Prévoyez une procédure de suppression sur demande (bouton fourni dans l'admin).
"""

import os
import io
import csv
import json
import sqlite3
import secrets
import datetime
from functools import wraps
from flask import (Flask, request, jsonify, Response, redirect, url_for,
                   session, render_template_string, send_file, abort)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FORGE_DB_PATH", os.path.join(BASE_DIR, "forge_crm.db"))
QUIZ_FILE = os.path.join(BASE_DIR, "forge-quiz-v8.html")

ADMIN_USER = os.environ.get("FORGE_ADMIN_USER", "forge")
ADMIN_PASSWORD = os.environ.get("FORGE_ADMIN_PASSWORD", "change-moi")
SECRET_KEY = os.environ.get("FORGE_SECRET_KEY", secrets.token_hex(32))

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Passe à True quand tu es en HTTPS (toujours en production) :
    SESSION_COOKIE_SECURE=os.environ.get("FORGE_HTTPS", "0") == "1",
    MAX_CONTENT_LENGTH=256 * 1024,   # 256 Ko max par soumission
)

# ----------------------------------------------------------------------
# Base de données (SQLite)
# ----------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT NOT NULL,
            prenom          TEXT,
            age             INTEGER,
            email           TEXT,
            metier          TEXT,
            activite        TEXT,
            senior          INTEGER,
            objectif        TEXT,
            objectifs_sec   TEXT,
            preference      TEXT,
            persona         TEXT,
            score_global    INTEGER,
            meilleur_axe    TEXT,
            axe_faible      TEXT,
            s_sommeil       REAL,
            s_forme         REAL,
            s_recup         REAL,
            s_stress        REAL,
            s_confort       REAL,
            s_nutrition     REAL,
            besoins         TEXT,
            newsletter      INTEGER,
            consent_recherche INTEGER,
            answers_json    TEXT,
            ip              TEXT,
            user_agent      TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()

# ----------------------------------------------------------------------
# Auth admin (simple, suffisant pour une petite équipe)
# ----------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("auth"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


# ----------------------------------------------------------------------
# Routes publiques
# ----------------------------------------------------------------------
@app.route("/")
def quiz():
    """Sert le questionnaire public."""
    try:
        with open(QUIZ_FILE, encoding="utf-8") as fh:
            return Response(fh.read(), mimetype="text/html")
    except FileNotFoundError:
        return Response("Questionnaire introuvable (forge-quiz-v8.html manquant).",
                        status=500, mimetype="text/plain")


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """Reçoit une soumission et l'enregistre. Renvoyé non-sensible."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "payload invalide"}), 400

    sc = data.get("scores") or {}
    row = {
        "created_at": data.get("submittedAt") or datetime.datetime.utcnow().isoformat() + "Z",
        "prenom": (data.get("prenom") or "")[:120],
        "age": _as_int(data.get("age")),
        "email": (data.get("email") or "")[:200],
        "metier": (data.get("metier") or "")[:200],
        "activite": (data.get("activite") or "")[:60],
        "senior": 1 if data.get("senior") else 0,
        "objectif": (data.get("objectifPrioritaire") or "")[:60],
        "objectifs_sec": json.dumps(data.get("objectifsSecondaires") or [], ensure_ascii=False),
        "preference": (data.get("preference") or "")[:60],
        "persona": (data.get("persona") or "")[:120],
        "score_global": _as_int(data.get("scoreGlobal")),
        "meilleur_axe": (data.get("meilleurAxe") or "")[:40],
        "axe_faible": (data.get("axeFaible") or "")[:40],
        "s_sommeil": _as_float(sc.get("sommeil")),
        "s_forme": _as_float(sc.get("forme")),
        "s_recup": _as_float(sc.get("recup")),
        "s_stress": _as_float(sc.get("stress")),
        "s_confort": _as_float(sc.get("confort")),
        "s_nutrition": _as_float(sc.get("nutrition")),
        "besoins": json.dumps(data.get("besoins") or [], ensure_ascii=False),
        "newsletter": 1 if data.get("newsletter") else 0,
        "consent_recherche": 1 if data.get("consentementRecherche") else 0,
        "answers_json": json.dumps(data.get("answers") or {}, ensure_ascii=False)[:60000],
        "ip": (request.headers.get("X-Forwarded-For", request.remote_addr) or "")[:80],
        "user_agent": (request.headers.get("User-Agent") or "")[:300],
    }
    cols = ",".join(row.keys())
    ph = ",".join("?" for _ in row)
    conn = get_db()
    cur = conn.execute(f"INSERT INTO submissions ({cols}) VALUES ({ph})", list(row.values()))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": new_id})


def _as_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _as_float(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        u = request.form.get("user", "")
        p = request.form.get("password", "")
        if secrets.compare_digest(u, ADMIN_USER) and secrets.compare_digest(p, ADMIN_PASSWORD):
            session["auth"] = True
            session["user"] = u
            nxt = request.args.get("next") or url_for("admin")
            return redirect(nxt)
        error = "Identifiants incorrects."
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------------------
# Interface privée (équipe)
# ----------------------------------------------------------------------
AXIS_LABELS = {"sommeil": "Sommeil", "forme": "Forme", "recup": "Récup.",
               "stress": "Stress", "confort": "Confort", "nutrition": "Nutrition"}


@app.route("/admin")
@login_required
def admin():
    q = (request.args.get("q") or "").strip()
    persona_f = (request.args.get("persona") or "").strip()
    consent_f = request.args.get("consent") or ""
    news_f = request.args.get("news") or ""

    where, params = [], []
    if q:
        where.append("(prenom LIKE ? OR email LIKE ? OR metier LIKE ? OR persona LIKE ?)")
        params += [f"%{q}%"] * 4
    if persona_f:
        where.append("persona LIKE ?")
        params.append(f"%{persona_f}%")
    if consent_f in ("0", "1"):
        where.append("consent_recherche = ?")
        params.append(int(consent_f))
    if news_f in ("0", "1"):
        where.append("newsletter = ?")
        params.append(int(news_f))
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    conn = get_db()
    rows = conn.execute(
        f"SELECT * FROM submissions {clause} ORDER BY id DESC LIMIT 500", params).fetchall()
    # stats globales (sur tout, pas seulement le filtre)
    total = conn.execute("SELECT COUNT(*) c FROM submissions").fetchone()["c"]
    news_count = conn.execute("SELECT COUNT(*) c FROM submissions WHERE newsletter=1").fetchone()["c"]
    rech_count = conn.execute("SELECT COUNT(*) c FROM submissions WHERE consent_recherche=1").fetchone()["c"]
    avg_global = conn.execute("SELECT AVG(score_global) a FROM submissions").fetchone()["a"]
    axis_avgs = conn.execute(
        "SELECT AVG(s_sommeil) so, AVG(s_forme) fo, AVG(s_recup) re, AVG(s_stress) st, "
        "AVG(s_confort) co, AVG(s_nutrition) nu FROM submissions").fetchone()
    top_personas = conn.execute(
        "SELECT persona, COUNT(*) c FROM submissions WHERE persona<>'' "
        "GROUP BY persona ORDER BY c DESC LIMIT 8").fetchall()
    conn.close()

    stats = {
        "total": total, "news": news_count, "rech": rech_count,
        "avg_global": round(avg_global) if avg_global else 0,
        "axes": {"Sommeil": axis_avgs["so"], "Forme": axis_avgs["fo"], "Récup.": axis_avgs["re"],
                 "Stress": axis_avgs["st"], "Confort": axis_avgs["co"], "Nutrition": axis_avgs["nu"]},
        "personas": top_personas,
    }
    return render_template_string(ADMIN_HTML, rows=rows, stats=stats,
                                  q=q, persona_f=persona_f, consent_f=consent_f, news_f=news_f,
                                  user=session.get("user"))


@app.route("/admin/<int:sub_id>")
@login_required
def admin_detail(sub_id):
    conn = get_db()
    r = conn.execute("SELECT * FROM submissions WHERE id=?", (sub_id,)).fetchone()
    conn.close()
    if not r:
        abort(404)
    answers = {}
    try:
        answers = json.loads(r["answers_json"] or "{}")
    except Exception:
        pass
    besoins = []
    try:
        besoins = json.loads(r["besoins"] or "[]")
    except Exception:
        pass
    scores = {"Sommeil": r["s_sommeil"], "Forme": r["s_forme"], "Récup.": r["s_recup"],
              "Stress": r["s_stress"], "Confort": r["s_confort"], "Nutrition": r["s_nutrition"]}
    return render_template_string(DETAIL_HTML, r=r, answers=answers, besoins=besoins, scores=scores)


@app.route("/admin/<int:sub_id>/delete", methods=["POST"])
@login_required
def admin_delete(sub_id):
    conn = get_db()
    conn.execute("DELETE FROM submissions WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/export.csv")
@login_required
def export_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM submissions ORDER BY id").fetchall()
    conn.close()
    out = io.StringIO()
    if rows:
        w = csv.writer(out)
        w.writerow(rows[0].keys())
        for r in rows:
            w.writerow([r[k] for k in r.keys()])
    data = out.getvalue().encode("utf-8-sig")  # BOM pour Excel
    fn = "forge_crm_" + datetime.date.today().isoformat() + ".csv"
    return send_file(io.BytesIO(data), mimetype="text/csv",
                     as_attachment=True, download_name=fn)


@app.route("/healthz")
def healthz():
    return "ok"


# ======================================================================
# Templates (noir & blanc, cohérents avec la D.A.)
# ======================================================================
BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#101010;color:#F5F5F5;line-height:1.5}
a{color:#F5F5F5}
.wrap{max-width:1180px;margin:0 auto;padding:24px}
.top{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,.14);padding-bottom:16px;margin-bottom:22px}
.brand{font-weight:700;letter-spacing:.28em;font-size:18px}
.muted{color:#9A9A9A}
.btn{display:inline-block;background:#fff;color:#101010;border:none;border-radius:9px;padding:9px 16px;font-weight:600;cursor:pointer;text-decoration:none;font-size:14px}
.btn.ghost{background:transparent;color:#F5F5F5;border:1.5px solid rgba(255,255,255,.3)}
.btn.sm{padding:6px 11px;font-size:13px}
.btn.danger{border-color:#C98B6B;color:#E7B597;background:transparent}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}
.card{background:#181818;border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:16px 18px;flex:1;min-width:150px}
.card .n{font-size:30px;font-weight:300}
.card .l{font-size:12px;color:#9A9A9A;text-transform:uppercase;letter-spacing:.08em}
.bar{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:13px}
.bar .lab{width:78px;color:#C9C9C9}
.bar .track{flex:1;height:8px;background:rgba(255,255,255,.08);border-radius:5px;overflow:hidden}
.bar .fill{height:100%;background:#fff;border-radius:5px}
.bar .v{width:40px;text-align:right;color:#C9C9C9}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:8px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid rgba(255,255,255,.08);white-space:nowrap}
th{color:#9A9A9A;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
tr:hover td{background:rgba(255,255,255,.03)}
.pill{display:inline-block;padding:2px 9px;border:1px solid rgba(255,255,255,.22);border-radius:20px;font-size:12px}
.score{font-weight:700}
form.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
input,select{background:#181818;border:1.5px solid rgba(255,255,255,.18);color:#F5F5F5;border-radius:9px;padding:9px 12px;font-size:14px;font-family:inherit}
input::placeholder{color:#777}
.kv{display:grid;grid-template-columns:200px 1fr;gap:8px 16px;font-size:14px;margin-top:10px}
.kv div:nth-child(odd){color:#9A9A9A}
.sect{margin:26px 0 10px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#9A9A9A;border-bottom:1px solid rgba(255,255,255,.1);padding-bottom:6px}
"""

LOGIN_HTML = """<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Forge — Espace équipe</title>
<style>""" + BASE_CSS + """
.login{max-width:360px;margin:12vh auto;background:#181818;border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:30px}
.login h1{font-weight:300;font-size:22px;margin-bottom:4px}
.login .brand{display:block;text-align:center;margin-bottom:18px}
.login input{width:100%;margin-bottom:12px}
.err{color:#E7B597;font-size:13px;margin-bottom:10px}
</style></head><body>
<div class=login>
  <span class=brand>F O R G E</span>
  <h1>Espace équipe</h1>
  <p class=muted style="font-size:13px;margin-bottom:18px">Accès réservé — données CRM</p>
  {% if error %}<div class=err>{{error}}</div>{% endif %}
  <form method=post>
    <input name=user placeholder="Identifiant" autocomplete=username autofocus>
    <input name=password type=password placeholder="Mot de passe" autocomplete=current-password>
    <button class=btn style="width:100%" type=submit>Se connecter</button>
  </form>
</div></body></html>"""

ADMIN_HTML = """<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Forge — CRM</title>
<style>""" + BASE_CSS + """</style></head><body><div class=wrap>
  <div class=top>
    <span class=brand>F O R G E · CRM</span>
    <span class=muted>{{user}} · <a href="{{url_for('logout')}}">déconnexion</a></span>
  </div>

  <div class=cards>
    <div class=card><div class=n>{{stats.total}}</div><div class=l>Soumissions</div></div>
    <div class=card><div class=n>{{stats.avg_global}}%</div><div class=l>Score global moyen</div></div>
    <div class=card><div class=n>{{stats.news}}</div><div class=l>Newsletter OK</div></div>
    <div class=card><div class=n>{{stats.rech}}</div><div class=l>Consentement recherche</div></div>
  </div>

  <div class=cards>
    <div class=card style="min-width:320px">
      <div class=l style="margin-bottom:8px">Moyenne par axe</div>
      {% for lab,val in stats.axes.items() %}
      <div class=bar><span class=lab>{{lab}}</span>
        <span class=track><span class=fill style="width:{{ (val or 0)|round|int }}%"></span></span>
        <span class=v>{{ (val or 0)|round|int }}%</span></div>
      {% endfor %}
    </div>
    <div class=card style="min-width:320px">
      <div class=l style="margin-bottom:8px">Personas les plus fréquents</div>
      {% for p in stats.personas %}
      <div class=bar><span class=lab style="width:auto;flex:1">{{p['persona']}}</span><span class=v>{{p['c']}}</span></div>
      {% else %}<div class=muted style="font-size:13px">Aucune donnée.</div>{% endfor %}
    </div>
  </div>

  <form class=filters method=get>
    <input name=q value="{{q}}" placeholder="Rechercher (prénom, email, métier, persona)">
    <input name=persona value="{{persona_f}}" placeholder="Persona contient…">
    <select name=news>
      <option value="" {{'selected' if news_f=='' else ''}}>Newsletter : tous</option>
      <option value="1" {{'selected' if news_f=='1' else ''}}>Newsletter : oui</option>
      <option value="0" {{'selected' if news_f=='0' else ''}}>Newsletter : non</option>
    </select>
    <select name=consent>
      <option value="" {{'selected' if consent_f=='' else ''}}>Recherche : tous</option>
      <option value="1" {{'selected' if consent_f=='1' else ''}}>Recherche : oui</option>
      <option value="0" {{'selected' if consent_f=='0' else ''}}>Recherche : non</option>
    </select>
    <button class=btn type=submit>Filtrer</button>
    <a class="btn ghost" href="{{url_for('admin')}}">Réinitialiser</a>
    <a class="btn ghost" href="{{url_for('export_csv')}}">⭳ Export CSV</a>
  </form>

  <table>
    <tr><th>#</th><th>Date</th><th>Prénom</th><th>Âge</th><th>Persona</th><th>Objectif</th>
        <th>Global</th><th>Faible</th><th>Email</th><th>News</th><th>Rech.</th><th></th></tr>
    {% for r in rows %}
    <tr>
      <td>{{r['id']}}</td>
      <td class=muted>{{ r['created_at'][:16].replace('T',' ') }}</td>
      <td>{{r['prenom']}}</td>
      <td>{{r['age'] or ''}}</td>
      <td><span class=pill>{{r['persona']}}</span></td>
      <td class=muted>{{r['objectif']}}</td>
      <td class=score>{{r['score_global'] if r['score_global'] is not none else ''}}%</td>
      <td class=muted>{{r['axe_faible']}}</td>
      <td class=muted>{{r['email']}}</td>
      <td>{{ '✓' if r['newsletter'] else '' }}</td>
      <td>{{ '✓' if r['consent_recherche'] else '' }}</td>
      <td><a class="btn ghost sm" href="{{url_for('admin_detail', sub_id=r['id'])}}">Voir</a></td>
    </tr>
    {% else %}
    <tr><td colspan=12 class=muted style="padding:24px">Aucune soumission pour l'instant.</td></tr>
    {% endfor %}
  </table>
  <p class=muted style="font-size:12px;margin-top:14px">500 dernières soumissions affichées · export CSV = toutes.</p>
</div></body></html>"""

DETAIL_HTML = """<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Forge — soumission #{{r['id']}}</title>
<style>""" + BASE_CSS + """</style></head><body><div class=wrap>
  <div class=top>
    <span class=brand>F O R G E · soumission #{{r['id']}}</span>
    <a class="btn ghost" href="{{url_for('admin')}}">← Retour</a>
  </div>

  <div class=cards>
    <div class=card style="flex:2;min-width:300px">
      <div class=l>Profil</div>
      <div class=kv>
        <div>Prénom</div><div>{{r['prenom']}}</div>
        <div>Âge</div><div>{{r['age']}}{{ ' · Senior' if r['senior'] else '' }}</div>
        <div>Métier</div><div>{{r['metier'] or '—'}}</div>
        <div>Email</div><div>{{r['email']}}</div>
        <div>Persona</div><div><span class=pill>{{r['persona']}}</span></div>
        <div>Activité</div><div>{{r['activite']}}</div>
        <div>Objectif prioritaire</div><div>{{r['objectif']}}</div>
        <div>Préférence</div><div>{{r['preference'] or '—'}}</div>
        <div>Newsletter</div><div>{{ 'Oui' if r['newsletter'] else 'Non' }}</div>
        <div>Consentement recherche</div><div>{{ 'Oui' if r['consent_recherche'] else 'Non' }}</div>
        <div>Date</div><div>{{ r['created_at'].replace('T',' ') }}</div>
      </div>
    </div>
    <div class=card style="flex:1;min-width:280px">
      <div class=l>Score global : <b style="color:#fff">{{r['score_global']}}%</b></div>
      <div style="margin-top:10px">
      {% for lab,val in scores.items() %}
        <div class=bar><span class=lab>{{lab}}</span>
          <span class=track><span class=fill style="width:{{ (val or 0)|round|int }}%"></span></span>
          <span class=v>{{ (val or 0)|round|int }}%</span></div>
      {% endfor %}
      </div>
    </div>
  </div>

  <div class=sect>Besoins identifiés (coulisse CRM)</div>
  <div>{% for b in besoins %}<span class=pill style="margin:3px">{{b}}</span>{% else %}<span class=muted>—</span>{% endfor %}</div>

  <div class=sect>Réponses brutes</div>
  <div class=kv>
    {% for k,v in answers.items() %}<div>{{k}}</div><div>{{v}}</div>{% endfor %}
  </div>

  <div class=sect>Zone RGPD</div>
  <form method=post action="{{url_for('admin_delete', sub_id=r['id'])}}"
        onsubmit="return confirm('Supprimer définitivement cette soumission ?');">
    <button class="btn danger sm" type=submit>Supprimer cette soumission (droit à l'effacement)</button>
  </form>
</div></body></html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
