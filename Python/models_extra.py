# models_extra.py
from datetime import datetime
from database import db  # ✅ on utilise la même instance

class CurrentMetric(db.Model):
    __tablename__ = "current_metrics"

    host_id = db.Column(db.Integer, nullable=False)
    oid = db.Column(db.String(200), nullable=False)
    metric = db.Column(db.String(120))
    value = db.Column(db.String(255))
    ts = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp(), nullable=False)
    meta = db.Column(db.JSON)

    __table_args__ = (db.PrimaryKeyConstraint("host_id", "oid"),)
