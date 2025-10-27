# models.py
from flask_login import UserMixin
from datetime import datetime
from database import db
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

# Tables associatives
host_tags = db.Table(
    "host_tags",
    db.metadata,
    db.Column("host_id", db.Integer, db.ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "operator", name="role_enum"), nullable=False, default="operator")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    receive_alerts = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    status = db.Column(db.String(20), default="unknown")
    snmp_community = db.Column(db.String(128), nullable=True, default="public")
    snmp_categories = db.Column(db.JSON, nullable=True)
    thresholds = db.Column(db.JSON, nullable=True, default={})

    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"))
    template_id = db.Column(db.Integer, db.ForeignKey("templates.id"))

    group = db.relationship("Group", backref=db.backref("hosts", lazy=True))
    template = db.relationship("Template", backref=db.backref("hosts", lazy=True))
    tags = db.relationship("Tag", secondary=host_tags, lazy="subquery",
                           backref=db.backref("hosts", lazy=True))

class CurrentMetric(db.Model):
    __tablename__ = "current_metrics"
    host_id = db.Column(db.Integer, db.ForeignKey("hosts.id"), primary_key=True)
    oid = db.Column(db.String(200), primary_key=True)
    metric = db.Column(db.String(120))
    value = db.Column(db.String(255), nullable=False)
    ts = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    meta = db.Column(db.JSON, nullable=True)

class Measurement(db.Model):
    __tablename__ = "measurements"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    host_id = db.Column(db.Integer, db.ForeignKey("hosts.id"), nullable=False)
    oid = db.Column(db.String(200))
    metric = db.Column(db.String(120))
    value = db.Column(db.String(255))
    meta = db.Column(db.JSON)
    ts = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class Alert(db.Model):
    __tablename__ = "alerts"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    host_id = db.Column(db.Integer, db.ForeignKey("hosts.id"))
    severity = db.Column(db.Enum("info", "warning", "critical", name="severity_enum"), nullable=False, default="info")
    message = db.Column(db.String(255), nullable=False)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    host = db.relationship("Host", backref=db.backref("alerts", lazy=True))
