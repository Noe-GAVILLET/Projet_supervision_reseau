# app.py
import os
import ipaddress
import hashlib
from functools import wraps
import random
from datetime import datetime, timedelta

from flask import Flask, render_template, redirect, url_for, request, session, flash, g, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import or_


# -----------------------------------------------------------------------------
# Config Flask + DB (adaptée à ton serveur MySQL Docker: 192.168.141.115:3002)
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

DB_HOST = os.getenv("DB_HOST", "192.168.141.115")
DB_PORT = os.getenv("DB_PORT", "3002")
DB_NAME = os.getenv("DB_NAME", "SNMP")
DB_USER = os.getenv("DB_USER", "sqluser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "sqluser_password")

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -----------------------------------------------------------------------------
# Modèles (alignés sur ton schéma SQL)
# -----------------------------------------------------------------------------
host_tags = db.Table(
    "host_tags",
    db.Column("host_id", db.Integer, db.ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "operator", name="role_enum"), nullable=False, default="operator")
    is_active = db.Column(db.Boolean, nullable=False, default=True)

class Group(db.Model):
    __tablename__ = "groups"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))

class Template(db.Model):
    __tablename__ = "templates"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.Text)
    snmp_version = db.Column(db.Enum("v1", "v2c", "v3", name="snmp_ver_enum"))
    params = db.Column(db.JSON)

class Tag(db.Model):
    __tablename__ = "tags"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Host(db.Model):
    __tablename__ = "hosts"
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.String(255))
    ip = db.Column(db.String(45), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=161)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"))
    template_id = db.Column(db.Integer, db.ForeignKey("templates.id"))

    group = db.relationship("Group", backref=db.backref("hosts", lazy=True))
    template = db.relationship("Template", backref=db.backref("hosts", lazy=True))
    tags = db.relationship("Tag", secondary=host_tags, lazy="subquery",
                           backref=db.backref("hosts", lazy=True))

class Alert(db.Model):
    __tablename__ = "alerts"
    id = db.Column(db.Integer, primary_key=True)
    host_id = db.Column(db.Integer, db.ForeignKey("hosts.id"), nullable=True)
    severity = db.Column(db.Enum("info", "warning", "critical", name="severity_enum"), nullable=False, default="info")
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    host = db.relationship("Host", backref=db.backref("alerts", lazy=True))

# Optionnel : ne pas forcer la création si le schéma existe déjà en BDD
#with app.app_context():
#    db.create_all()

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
    1) Tente d'abord la vérification Werk­zeug (gère scrypt, pbkdf2, etc.).
    2) Fallback : compare à un SHA256 hex uppercase (cas de ton admin SQL d'origine).
    """
    try:
        if check_password_hash(stored_hash, password_plain):
            return True
    except Exception:
        pass
    h = hashlib.sha256(password_plain.encode("utf-8")).hexdigest().upper()
    return h == stored_hash

def seed_fake_alerts(n=12):
    """Génère des fausses alertes si la table est vide (dev)."""
    hosts = Host.query.all()
    if not hosts:
        demo = Host(hostname="demo-sw1", ip="192.168.0.10", port=161, description="Host de démonstration")
        db.session.add(demo)
        db.session.commit()
        hosts = [demo]

    severities = ["info", "warning", "critical"]
    messages = [
        "CPU usage high", "Temp threshold exceeded", "Interface down",
        "SNMP timeout", "Disk space low", "Link flapping",
        "Device unreachable", "Config change detected",
    ]
    now = datetime.utcnow()
    fake = []
    for _ in range(n):
        h = random.choice(hosts)
        sev = random.choices(severities, weights=[2, 3, 1])[0]  # plus de warnings
        msg = random.choice(messages)
        ts = now - timedelta(minutes=random.randint(1, 24 * 60))
        fake.append(Alert(host_id=h.id, severity=sev, message=f"{h.hostname}: {msg}", created_at=ts))
    db.session.add_all(fake)
    db.session.commit()


@app.before_request
def load_user():
    g.user = session.get("username")
    g.role = session.get("role", None)

@app.context_processor
def inject_auth():
    return {"current_user": g.user, "current_role": g.role}

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def home():
    return redirect(url_for("admin") if g.user else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        user = User.query.filter_by(username=u, is_active=True).first()
        if user and verify_password(user.password_hash, p):
            session["username"] = user.username
            session["role"] = user.role
            flash(f"Bienvenue, {user.username} !", "success")
            return redirect(request.args.get("next") or url_for("admin"))
        flash("Identifiants invalides.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté.", "info")
    return redirect(url_for("login"))

@app.route("/hosts")
@login_required
def hosts_list():
    hosts = Host.query.order_by(Host.hostname.asc()).all()
    return render_template("admin.html", hosts=hosts, title="Liste des hôtes")

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
@login_required
def alerts():
    alerts_q = Alert.query.order_by(Alert.created_at.desc())
    alerts = alerts_q.all()

    # Seed auto si vide (désactivable via SEED_FAKE_ALERTS=0)
    if not alerts and os.getenv("SEED_FAKE_ALERTS", "1") == "1":
        seed_fake_alerts()
        alerts = alerts_q.all()

    return render_template("alerts.html", alerts=alerts)


@app.route("/healthz")
def healthz():
    # petite route santé pour vérifier la connexion
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception as e:
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
    host = db.session.get(Host, host_id)
    if not host:
        abort(404)
    return render_template("host_detail.html", host=host)

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
        template_id = request.form.get("template_id") or None
        ip = request.form.get("ip", "").strip()
        port = request.form.get("port", "161").strip()
        tags_raw = request.form.get("tags", "").strip()

        if not hostname:
            flash("Hostname obligatoire.", "danger")
            return render_template("host_edit.html", host=host, groups=groups, templates=templates)

        # Unicité hostname (autoriser le même pour ce host)
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

        # Appliquer les modifications
        host.hostname = hostname
        host.description = description
        host.ip = ip
        host.port = port
        host.group_id = int(group_id) if group_id else None
        host.template_id = int(template_id) if template_id else None

        # Tags (remplacement complet)
        new_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
        new_tags = []
        for name in new_names:
            tag = Tag.query.filter_by(name=name).first()
            if not tag:
                tag = Tag(name=name)
            new_tags.append(tag)
        host.tags = new_tags  # remplace l’ensemble

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
    hosts = Host.query.order_by(Host.hostname.asc()).all()
    return render_template("admin.html", hosts=hosts)

@app.route("/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def user_new():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip() or None
        password = request.form.get("password", "")
        role = request.form.get("role", "operator")
        is_active = True if request.form.get("is_active") == "on" else False

        # Validations simples
        if not username or not password:
            flash("Utilisateur et mot de passe sont obligatoires.", "danger")
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

        # Hash fort (pbkdf2 de Werkzeug)
        pwd_hash = generate_password_hash(password)

        user = User(
            username=username,
            email=email,
            password_hash=pwd_hash,
            role=role,
            is_active=is_active
        )
        db.session.add(user)
        db.session.commit()

        flash(f"Compte « {username} » créé avec succès.", "success")
        return redirect(url_for("admin"))

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
        template_id = request.form.get("template_id") or None
        ip = request.form.get("ip", "").strip()
        port = request.form.get("port", "161").strip()
        tags_raw = request.form.get("tags", "").strip()

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
            template_id=int(template_id) if template_id else None,
        )

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
# Lancement
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
