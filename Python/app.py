import os
import csv
import re
import ipaddress
import hashlib
import random
from io import TextIOWrapper
from datetime import datetime, timedelta
from functools import wraps
from typing import List, Optional
from snmp_utils import snmp_get, snmp_walk, get_metrics
from models import User, Host, Alert, Group, Tag, Template, CurrentMetric, Measurement, host_tags
from seuils import get_severity

# --- Flask / SQLAlchemy / Security ---
from flask import (
    Flask, Response, render_template, redirect, url_for,
    request, session, flash, g, jsonify, abort
)
from database import db
from sqlalchemy import or_, func, case
from werkzeug.security import check_password_hash, generate_password_hash

# ----------------------------------------------------------------------------- 
# Config Flask + DB 
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "4tre84t9ret4ert")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3002")
DB_NAME = os.getenv("DB_NAME", "SNMP")
DB_USER = os.getenv("DB_USER", "sqluser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "sqluser_password")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ✅ Lier directement db à app (pas de init_app)
db.init_app(app)

# Optionnel : ne pas forcer la création si le schéma existe déjà en BDD
# with app.app_context():
#     db.create_all()

# -----------------------------------------------------------------------------
# Auth via BDD
# -----------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login", next=request.path))
        if session.get("role") != "admin":
            flash("Accès réservé aux administrateurs.", "warning")
            return redirect(url_for("admin"))
        return view(*args, **kwargs)
    return wrapped

def verify_password(stored_hash: str, password_plain: str) -> bool:
    """
    1) Tente d'abord la vérification Werkzeug.
    2) Fallback : SHA256 hex uppercase (cas de l'admin SQL d'origine).
    """
    try:
        if check_password_hash(stored_hash, password_plain):
            return True
    except Exception:
        pass
    h = hashlib.sha256(password_plain.encode("utf-8")).hexdigest().upper()
    return h == stored_hash

def _split_tags(raw: str) -> List[str]:
    """Sépare prod,router|snmpv2;edge -> ['prod','router','snmpv2','edge']"""
    if not raw:
        return []
    parts = re.split(r"[,\|;]", raw)
    return [p.strip() for p in parts if p and p.strip()]

def _ensure_group(name: str) -> Optional[Group]:
    if not name:
        return None
    grp = Group.query.filter_by(name=name).first()
    if not grp:
        grp = Group(name=name)
        db.session.add(grp)
        db.session.flush()
    return grp

def _ensure_template(name: str) -> Optional[Template]:
    if not name:
        return None
    tpl = Template.query.filter_by(name=name).first()
    if not tpl:
        tpl = Template(name=name)
        db.session.add(tpl)
        db.session.flush()
    return tpl

def get_down_hostnames():
    critical_alerts = (
        Alert.query
        .filter(
            Alert.severity == "critical",
            Alert.message.like("%ping échoué%"),
            Alert.resolved_at.is_(None)
        )
        .all()
    )
    return {a.host.hostname for a in critical_alerts if a.host}


@app.before_request
def load_user():
    g.user = session.get("username")
    g.role = session.get("role")

    if g.user:
        user = User.query.filter_by(username=g.user, is_active=True).first()
        if not user:
            session.clear()
            return redirect(url_for("login"))

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("admin") if g.user else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    # Si l'utilisateur est déjà connecté via session
    if session.get("username"):
        return redirect(url_for("admin"))

    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")

        user = User.query.filter_by(username=u, is_active=True).first()

        if user and verify_password(user.password_hash, p):
            # ✅ Authentification maison
            session["username"] = user.username
            session["role"] = user.role
            flash(f"Bienvenue, {user.username} !", "success")

            next_page = request.args.get("next")
            return redirect(next_page or url_for("admin"))

        flash("Identifiants invalides.", "danger")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    # ✅ Déconnexion maison
    session.clear()
    flash("Déconnecté avec succès.", "info")
    return redirect(url_for("login"))

@app.route("/hosts")
@login_required
def hosts_list():
    hosts = Host.query.order_by(Host.hostname.asc()).all()

    # 🔹 Cherche alertes critiques récentes (< 5 min)
    recent_criticals = (
        Alert.query
        .filter(
            Alert.severity == "critical",
            Alert.created_at >= datetime.utcnow() - timedelta(minutes=5)
        )
        .all()
    )

    down_hosts = []
    up_hosts = []
    unknown_hosts = []

    for h in hosts:
        if h.snmp_categories:
            if h.hostname in get_down_hostnames():  # ou autre logique
                down_hosts.append(h)
            else:
                up_hosts.append(h)
        else:
            unknown_hosts.append(h)

    return render_template(
    "admin.html",
    hosts=hosts,
    down_hosts=[h.hostname for h in down_hosts],
    stats={
        "total_hosts": len(hosts),
        "up": len(up_hosts),
        "down": len(down_hosts),
        "unknown": len(unknown_hosts),
        "by_category": {}
    }
)

@app.route("/hosts/search")
@login_required
def hosts_search():
    q = request.args.get("q", "").strip()

    hosts = []
    if q:
        query = (db.session.query(Host)
                 .outerjoin(Group, Host.group)
                 .outerjoin(Template, Host.template)
                 .outerjoin(host_tags)
                 .outerjoin(Tag))
        hosts = (query.filter(or_(
                    Host.hostname.ilike(f"%{q}%"),
                    Host.ip.ilike(f"%{q}%"),
                    Group.name.ilike(f"%{q}%"),
                    Template.name.ilike(f"%{q}%"),
                    Tag.name.ilike(f"%{q}%"),
                 ))
                 .distinct()
                 .order_by(Host.hostname.asc())
                 .all())
    return render_template("hosts_search.html", q=q, hosts=hosts)

@app.route("/alerts")
def alerts():
    severity = request.args.get("severity")
    q = request.args.get("q")
    status = request.args.get("status", "all")  

    query = Alert.query.join(Host, isouter=True)

    # --- Filtre gravité ---
    if severity:
        query = query.filter(Alert.severity == severity)

    # --- Filtre recherche host ---
    if q:
        query = query.filter(Host.hostname.ilike(f"%{q}%"))

    # --- Filtre statut ---
    if status == "active":
        query = query.filter(Alert.resolved_at == None)
    elif status == "resolved":
        query = query.filter(Alert.resolved_at.isnot(None))
    # sinon ("all") → pas de filtre

    # --- Tri : actives en haut, puis résolues ---
    alerts = query.order_by(Alert.created_at.desc()).all()

    return render_template("alerts.html", alerts=alerts, severity=severity, q=q, status=status)

@app.route("/healthz")
def healthz():
    # petite route santé pour vérifier la connexion
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return jsonify(
        status="ok" if db_ok else "degraded",
        db_host=DB_HOST,
        db_port=DB_PORT,
        db_name=DB_NAME,
        user=g.user,
        role=g.role,
    )

@app.route("/hosts/<int:host_id>")
@login_required
def host_view(host_id: int):
    from models import CurrentMetric
    from snmp_utils import SYSTEM_OID_LABELS, format_sysuptime  # 🔽 Ajoute cette ligne

    host = db.session.get(Host, host_id)
    if not host:
        abort(404)

    metrics = {}
    system_data = []
    error = None

    try:
        # 🔹 Tentative d’interrogation SNMP live
        if host.snmp_categories:
            for category in host.snmp_categories:
                metrics[category] = get_metrics(
                    ip=host.ip,
                    community=host.snmp_community,
                    port=host.port,
                    category=category
                )
    except Exception as e:
        error = f"Hôte injoignable ou timeout SNMP : {e}"

    # 🔹 Si le live échoue → on récupère depuis la BDD
    if not metrics:
        rows = CurrentMetric.query.filter_by(host_id=host.id).all()
        if rows:
            for r in rows:
                cat = r.meta if isinstance(r.meta, str) else (r.meta or "autre")
                metrics.setdefault(cat, {})[r.oid] = r.value
        else:
            error = error or "Aucune métrique disponible (host jamais contacté)."

    # 🔸 Extraire system_data lisible à partir des OIDs de la catégorie "system"
    if "system" in metrics:
        for oid, value in metrics["system"].items():
            label = SYSTEM_OID_LABELS.get(oid, oid)
            if oid == '1.3.6.1.2.1.1.3.0':  # uptime
                value = format_sysuptime(value)
            system_data.append((label, value))

    return render_template(
        "host_detail.html",
        host=host,
        metrics=metrics,
        system_data=system_data,
        error=error
    )

@app.route("/hosts/<int:host_id>/edit", methods=["GET", "POST"])
@login_required
def host_edit(host_id: int):
    host = db.session.get(Host, host_id)
    if not host:
        abort(404)

    groups = Group.query.order_by(Group.name.asc()).all()
    templates = Template.query.order_by(Template.name.asc()).all()

    if request.method == "POST":
        hostname = request.form.get("hostname", "").strip()
        description = request.form.get("description", "").strip()
        group_id = request.form.get("group_id") or None
        template_id = request.form.get("template_id") or None  # ok si tu gardes le champ
        ip = request.form.get("ip", "").strip()
        port = request.form.get("port", "161").strip()
        tags_raw = request.form.get("tags", "").strip()

        # SNMP v2c
        snmp_community = request.form.get("snmp_community", "public").strip()
        raw_categories = request.form.getlist("snmp_categories[]")  # <<< IMPORTANT
        allowed = {"system", "cpu", "ram", "storage", "interfaces"}
        snmp_categories = [c for c in raw_categories if c in allowed]
        if not snmp_categories:
            snmp_categories = ["system"]

        # Validations
        if not hostname:
            flash("Hostname obligatoire.", "danger")
            return render_template("host_edit.html", host=host, groups=groups, templates=templates)

        exists = Host.query.filter(Host.hostname == hostname, Host.id != host.id).first()
        if exists:
            flash("Un autre host utilise déjà ce hostname.", "warning")
            return render_template("host_edit.html", host=host, groups=groups, templates=templates)

        try:
            ipaddress.ip_address(ip)
        except ValueError:
            flash("Adresse IP invalide.", "danger")
            return render_template("host_edit.html", host=host, groups=groups, templates=templates)

        try:
            port = int(port)
            if port < 1 or port > 65535:
                raise ValueError()
        except ValueError:
            flash("Port invalide (1-65535).", "danger")
            return render_template("host_edit.html", host=host, groups=groups, templates=templates)

        # Appliquer les modifications (affecter de NOUVELLES valeurs)
        host.hostname = hostname
        host.description = description
        host.ip = ip
        host.port = port
        host.group_id = int(group_id) if group_id else None
        host.template_id = int(template_id) if template_id else None
        host.snmp_community = snmp_community or "public"
        host.snmp_categories = list(snmp_categories)  # <<< nouvelle liste pour bien “dirty” la colonne JSON

        # Tags (remplacement complet)
        new_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
        new_tags = []
        for name in new_names:
            tag = Tag.query.filter_by(name=name).first()
            if not tag:
                tag = Tag(name=name)
            new_tags.append(tag)
        host.tags = new_tags

        db.session.commit()
        flash(f"Host « {host.hostname} » mis à jour.", "success")
        return redirect(url_for("admin"))

    # Pré-remplir le champ tags
    tags_value = ", ".join(t.name for t in host.tags) if host.tags else ""
    return render_template("host_edit.html", host=host, groups=groups, templates=templates, tags_value=tags_value)



@app.route("/hosts/<int:host_id>/delete", methods=["POST"])
@login_required
def host_delete(host_id: int):
    host = db.session.get(Host, host_id)
    if not host:
        abort(404)
    hostname = host.hostname
    db.session.delete(host)
    db.session.commit()
    flash(f"Host « {hostname} » supprimé.", "success")
    return redirect(url_for("admin"))

@app.route("/admin")
@login_required
def admin():
    from models import Host, Alert
    from sqlalchemy import or_

    # Liste complète des hôtes
    hosts = Host.query.order_by(Host.hostname.asc()).all()
    

    # Comptages par statut
    total_hosts = len(hosts)
    hosts_up = Host.query.filter_by(status="up").count()
    hosts_down = Host.query.filter_by(status="down").count()
    hosts_warning = Host.query.filter_by(status="warning").count()
    hosts_unknown = Host.query.filter(
        or_(Host.status == None, Host.status == "unknown")
    ).count()

    # Répartition par catégorie SNMP
    by_category = {}
    for h in hosts:
        if not h.snmp_categories:
            continue
        for cat in h.snmp_categories:
            by_category[cat] = by_category.get(cat, 0) + 1

    # Dernières alertes (optionnel)
    try:
        alerts = Alert.query.order_by(Alert.created_at.desc()).limit(5).all()
    except Exception:
        alerts = []

    # Préparation du dictionnaire de stats (si besoin ailleurs)
    stats = {
        "total_hosts": total_hosts,
        "up": hosts_up,
        "down": hosts_down,
        "warning": hosts_warning,
        "unknown": hosts_unknown,
        "by_category": by_category,
    }

    return render_template(
        "admin.html",
        hosts=hosts,
        total_hosts=total_hosts,
        hosts_up=hosts_up,
        hosts_down=hosts_down,
        hosts_warning=hosts_warning,
        hosts_unknown=hosts_unknown,
        stats=stats,
        alerts=alerts
    )


from datetime import datetime
from werkzeug.security import generate_password_hash

@app.route("/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def user_new():
    from models import User

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip() or None
        password = request.form.get("password", "")
        role = request.form.get("role", "operator")
        is_active = "is_active" in request.form
        receive_alerts = "receive_alerts" in request.form  # ✅ nouveau champ

        # Validation de base
        if not username or not password:
            flash("Nom d’utilisateur et mot de passe sont obligatoires.", "danger")
            return render_template("user_new.html")

        if role not in ("admin", "operator"):
            flash("Rôle invalide.", "danger")
            return render_template("user_new.html")

        if User.query.filter_by(username=username).first():
            flash("Ce nom d’utilisateur existe déjà.", "warning")
            return render_template("user_new.html")

        if email and User.query.filter_by(email=email).first():
            flash("Cet email est déjà utilisé.", "warning")
            return render_template("user_new.html")

        pwd_hash = generate_password_hash(password)

        user = User(
            username=username,
            email=email,
            password_hash=pwd_hash,
            role=role,
            is_active=is_active,
            receive_alerts=receive_alerts,  # ✅ nouveau champ
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.session.add(user)
        db.session.commit()

        flash(f"Compte « {username} » créé avec succès ✅", "success")
        return redirect(url_for("user_list"))

    return render_template("user_new.html")


# ---------- Groupes ----------
@app.route("/groups/new", methods=["GET", "POST"])
@login_required
def group_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("Le nom de groupe est obligatoire.", "danger")
            return render_template("group_new.html")
        if Group.query.filter_by(name=name).first():
            flash("Ce groupe existe déjà.", "warning")
            return render_template("group_new.html")
        db.session.add(Group(name=name, description=description))
        db.session.commit()
        flash(f"Groupe « {name} » créé.", "success")
        return redirect(url_for("host_new"))
    return render_template("group_new.html")

# ---------- Templates ----------
@app.route("/templates/new", methods=["GET", "POST"])
@login_required
def template_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("Le nom du template est obligatoire.", "danger")
            return render_template("template_new.html")
        if Template.query.filter_by(name=name).first():
            flash("Ce template existe déjà.", "warning")
            return render_template("template_new.html")
        db.session.add(Template(name=name, description=description))
        db.session.commit()
        flash(f"Template « {name} » créé.", "success")
        return redirect(url_for("host_new"))
    return render_template("template_new.html")

@app.get("/hosts/import/template")
@login_required
def hosts_import_template():
    """Télécharge un modèle CSV."""
    lines = [
        # Ajoute les nouvelles colonnes en commentaire d’exemple (non obligatoires)
        ["hostname", "description", "group", "ip", "port", "template", "tags", "snmp_community", "snmp_categories"],
        ["sw-core-1", "Switch cœur", "Network", "192.168.10.10", "161", "Default", "prod|layer2", "public", "system|interfaces"],
        ["srv-monitor", "Serveur Monitor", "Servers", "192.168.20.15", "161", "Linux", "prod|snmpv2", "public", "system|cpu|storage|interfaces"],
    ]
    def _gen():
        out = []
        for row in lines:
            out.append(",".join(row))
        return "\n".join(out) + "\n"

    return Response(_gen(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=hosts_template.csv"})

@app.route("/hosts/import", methods=["GET", "POST"])
@login_required
def hosts_import():
    report = None
    if request.method == "POST":
        f = request.files.get("file")
        if not f or f.filename == "":
            flash("Aucun fichier sélectionné.", "warning")
            return render_template("hosts_import.html", report=None)

        if not f.filename.lower().endswith(".csv"):
            flash("Format invalide : seul le .csv est accepté.", "danger")
            return render_template("hosts_import.html", report=None)

        # Lecture UTF-8 (gère BOM via utf-8-sig)
        f.stream.seek(0)
        wrapper = TextIOWrapper(f.stream, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(wrapper)

        missing_cols = [c for c in ["hostname", "ip"] if c not in reader.fieldnames]
        if missing_cols:
            flash(f"Colonnes obligatoires manquantes: {', '.join(missing_cols)}.", "danger")
            return render_template("hosts_import.html", report=None)

        created, skipped, errors = 0, 0, []
        seen_hostnames = set()

        try:
            for lineno, row in enumerate(reader, start=2):  # ligne 1 = header
                hostname = (row.get("hostname") or "").strip()
                description = (row.get("description") or "").strip()
                group_name = (row.get("group") or "").strip()
                ip = (row.get("ip") or "").strip()
                port_raw = (row.get("port") or "161").strip()
                template_name = (row.get("template") or "").strip()
                tags_raw = (row.get("tags") or "").strip()

                # SNMP v2c (optionnels)
                snmp_community = (row.get("snmp_community") or "public").strip()
                cats_raw = (row.get("snmp_categories") or "system").strip()
                snmp_categories = [c.strip() for c in re.split(r"[,\|;]", cats_raw) if c.strip()]

                # validations
                if not hostname:
                    errors.append(f"L{lineno}: hostname manquant.")
                    skipped += 1
                    continue
                if hostname in seen_hostnames:
                    errors.append(f"L{lineno}: hostname dupliqué dans le CSV ({hostname}).")
                    skipped += 1
                    continue
                seen_hostnames.add(hostname)

                if Host.query.filter_by(hostname=hostname).first():
                    errors.append(f"L{lineno}: hostname déjà présent en BDD ({hostname}), ignoré.")
                    skipped += 1
                    continue

                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    errors.append(f"L{lineno}: IP invalide ({ip}).")
                    skipped += 1
                    continue

                try:
                    port = int(port_raw)
                    if port < 1 or port > 65535:
                        raise ValueError()
                except ValueError:
                    errors.append(f"L{lineno}: port invalide ({port_raw}).")
                    skipped += 1
                    continue

                grp = _ensure_group(group_name)
                tpl = _ensure_template(template_name)

                host = Host(
                    hostname=hostname,
                    description=description,
                    ip=ip,
                    port=port,
                    group_id=grp.id if grp else None,
                    template_id=tpl.id if tpl else None,
                )

                # SNMP v2c
                host.snmp_community = snmp_community or "public"
                host.snmp_categories = snmp_categories or ["system"]

                # tags
                for tname in _split_tags(tags_raw):
                    tag = Tag.query.filter_by(name=tname).first()
                    if not tag:
                        tag = Tag(name=tname)
                    host.tags.append(tag)

                db.session.add(host)
                created += 1

            db.session.commit()
            report = {"created": created, "skipped": skipped, "errors": errors, "total": created + skipped}

        except Exception as e:
            db.session.rollback()
            flash(f"Erreur pendant l'import: {e}", "danger")
            report = None

    return render_template("hosts_import.html", report=report)


@app.route("/users/<int:user_id>")
@login_required
def user_profile(user_id):
    from models import User
    user = User.query.get_or_404(user_id)
    return render_template("user_profile.html", user=user)

@app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def user_edit(user_id):
    from models import User
    user = User.query.get_or_404(user_id)

    # Seuls les administrateurs peuvent modifier un utilisateur
    if g.role != "admin":
        flash("Accès refusé : réservé aux administrateurs.", "danger")
        return redirect(url_for("user_profile", user_id=user.id))

    if request.method == "POST":
        user.username = request.form.get("username", user.username)
        user.email = request.form.get("email", user.email)
        user.role = request.form.get("role", user.role)
        user.is_active = "is_active" in request.form
        user.receive_alerts = "receive_alerts" in request.form
        user.updated_at = datetime.utcnow()

        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if new_password:
            if new_password != confirm_password:
                flash("Les mots de passe ne correspondent pas.", "danger")
                return render_template("user_edit.html", user=user)
            user.password_hash = generate_password_hash(new_password)
            flash("Mot de passe mis à jour avec succès ✅", "success")

        db.session.commit()
        flash("Profil mis à jour avec succès ✅", "success")
        return redirect(url_for("user_list"))

    return render_template("user_edit.html", user=user)

@app.route("/users")
@login_required
@admin_required
def user_list():
    users = User.query.order_by(User.username.asc()).all()
    return render_template("user_list.html", users=users)

@app.route("/groups/<int:group_id>")
@login_required
def group_hosts(group_id):
    from models import Group, Host

    group = Group.query.get_or_404(group_id)
    hosts = Host.query.filter_by(group_id=group.id).order_by(Host.hostname.asc()).all()

    # Aucun champ "status" → on met des valeurs par défaut
    total_hosts = len(hosts)
    stats = {
        "total_hosts": total_hosts,
        "up": 0,
        "down": 0,
        "unknown": total_hosts
    }

    return render_template(
        "admin.html",
        hosts=hosts,
        title=f"Groupe : {group.name}",
        selected_group=group,
        stats=stats
    )


@app.route("/category/<string:category>")
@login_required
def category_overview(category):
    from models import Host
    from snmp_utils import get_metrics

    # Récupère les hôtes surveillant cette catégorie
    hosts = Host.query.filter(Host.snmp_categories.like(f"%{category}%")).all()

    host_data = []
    for h in hosts:
        try:
            metrics = get_metrics(h.ip, h.snmp_community or "public", h.port or 161, category)
            host_data.append({"host": h, "metrics": metrics})
        except Exception as e:
            host_data.append({"host": h, "error": str(e)})

    return render_template("category_view.html", category=category, hosts=host_data)

# ---------- Hosts ----------
@app.route("/hosts/new", methods=["GET", "POST"])
@login_required
def host_new():
    groups = Group.query.order_by(Group.name.asc()).all()
    templates = Template.query.order_by(Template.name.asc()).all()

    if request.method == "POST":
        hostname = request.form.get("hostname", "").strip()
        description = request.form.get("description", "").strip()
        group_id = request.form.get("group_id") or None
        ip = request.form.get("ip", "").strip()
        port = request.form.get("port", "161").strip()
        tags_raw = request.form.get("tags", "").strip()

        # SNMP v2c (form)
        snmp_community = request.form.get("snmp_community", "public").strip()
        snmp_categories = request.form.getlist("snmp_categories")

        # Validations simples
        if not hostname:
            flash("Hostname obligatoire.", "danger")
            return render_template("host_new.html", groups=groups, templates=templates)
        if Host.query.filter_by(hostname=hostname).first():
            flash("Un host avec ce hostname existe déjà.", "warning")
            return render_template("host_new.html", groups=groups, templates=templates)

        try:
            ipaddress.ip_address(ip)
        except ValueError:
            flash("Adresse IP invalide.", "danger")
            return render_template("host_new.html", groups=groups, templates=templates)

        try:
            port = int(port)
            if port < 1 or port > 65535:
                raise ValueError()
        except ValueError:
            flash("Port invalide (1-65535).", "danger")
            return render_template("host_new.html", groups=groups, templates=templates)

        host = Host(
            hostname=hostname,
            description=description,
            ip=ip,
            port=port,
            group_id=int(group_id) if group_id else None,
        )

        # SNMP v2c
        host.snmp_community = snmp_community or "public"
        host.snmp_categories = snmp_categories or ["system"]

        # Tags (séparés par des virgules)
        tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
        for name in tag_names:
            tag = Tag.query.filter_by(name=name).first()
            if not tag:
                tag = Tag(name=name)
            host.tags.append(tag)

        db.session.add(host)
        db.session.commit()
        flash(f"Host « {hostname} » créé.", "success")
        return redirect(url_for("admin"))

    return render_template("host_new.html", groups=groups, templates=templates)



# -----------------------------------------------------------------------------
# Enregistrement des Blueprints API (SNMP poll dans api_poll.py)
# -----------------------------------------------------------------------------
# IMPORTANT : api_poll.py NE DOIT PAS importer 'app' pour éviter les imports circulaires.
# Il doit uniquement utiliser 'from flask import Blueprint' et accéder aux modèles via import local propre.
try:
    from api_poll import bp as api_poll_bp
    app.register_blueprint(api_poll_bp)
except Exception as e:
    # Evite de casser l'app si le blueprint n'est pas encore créé
    app.logger.warning(f"api_poll blueprint non chargé: {e}")

# ----------------------------------------------------------------------------- 
# Scheduler SNMP (démarre après les modèles)
# -----------------------------------------------------------------------------
from poller import start_scheduler

with app.app_context():
    start_scheduler(app, db, Host, Alert)

# -----------------------------------------------------------------------------
# Contexte global pour la navbar
# -----------------------------------------------------------------------------
from routes import logs
app.register_blueprint(logs.bp)

from flask import g

from models import CurrentMetric

@app.context_processor
def inject_global_state():
    """Injecte dans tous les templates la liste des hosts down."""
    try:
        down_hosts = (
            CurrentMetric.query
            .filter(CurrentMetric.meta == "interfaces", CurrentMetric.value == "Down")
            .with_entities(CurrentMetric.host_id)
            .distinct()
            .all()
        )
        down_ids = [h.host_id for h in down_hosts]
        hosts_down = Host.query.filter(Host.id.in_(down_ids)).all()
    except Exception:
        hosts_down = []

    return dict(hosts_down=hosts_down)


def inject_auth():
    return {"current_user": g.user, "current_role": g.role}

def inject_groups():
    try:
        groups = Group.query.order_by(Group.name.asc()).all()
    except Exception:
        groups = []
    return dict(groups=groups)

def inject_globals():
    from models import Group, Alert
    groups = Group.query.order_by(Group.name.asc()).all()
    recent_alerts = Alert.query.filter(Alert.created_at >= datetime.utcnow() - timedelta(hours=1)).count()
    return dict(groups=groups, alert_count=recent_alerts)
# -------------------------------------------------------
# 🔄 Injection du cache d'état des hôtes dans les templates
# -------------------------------------------------------
@app.context_processor
def inject_host_status_cache():
    try:
        from poller import HOST_STATUS_CACHE
        return {'HOST_STATUS_CACHE': HOST_STATUS_CACHE}
    except Exception:
        # si poller pas encore initialisé
        return {'HOST_STATUS_CACHE': {}}

@app.context_processor
def inject_user():
    """Rend current_user et current_role disponibles dans tous les templates."""
    return dict(current_user=g.user, current_role=g.role)

def inject_severity_utils():
    return dict(get_severity=get_severity)

# -----------------------------------------------------------------------------
# Lancement
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        with app.app_context():
            from poller import start_scheduler
            start_scheduler(app, db, Host, Alert)
    else:
        print("[poller] ⏭️ Scheduler non démarré (process reloader Flask)")

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)