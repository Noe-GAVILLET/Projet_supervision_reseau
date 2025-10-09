# db_utils.py
from datetime import datetime

# ⚠️ Import différé pour éviter le circular import
def upsert_current_metric(db, host_id, oid, metric, value, meta=None):
    """Insère ou met à jour une métrique SNMP courante."""
    from models_extra import CurrentMetric  # import local

    record = CurrentMetric.query.filter_by(host_id=host_id, oid=oid).first()

    if not record:
        record = CurrentMetric(host_id=host_id, oid=oid)
        db.session.add(record)

    record.metric = metric
    record.value = value
    record.ts = datetime.utcnow()
    record.meta = meta
    db.session.commit()
    return record


def open_alert(db, Alert, host_id, severity, message):
    """Crée une alerte dans la table alerts (sans import circulaire)."""
    alert = Alert(host_id=host_id, severity=severity, message=message)
    db.session.add(alert)
    db.session.commit()
    print(f"[db_utils] 🚨 Alerte créée pour host_id={host_id}: {severity} - {message}")