import json
from models import CurrentMetric, Measurement, Alert
from datetime import datetime

def upsert_current_metric(db, host_id, oid, metric, value, meta=None):
    """Insère ou met à jour la dernière valeur connue d'une métrique pour un host."""

    # 🔧 Correction : sérialise en JSON les objets complexes
    if isinstance(meta, (dict, list)):
        meta = json.dumps(meta)
    if isinstance(value, (dict, list)):
        value = json.dumps(value)

    existing = CurrentMetric.query.filter_by(host_id=host_id, oid=oid).first()
    if existing:
        existing.value = value
        existing.metric = metric
        existing.ts = datetime.utcnow()
        existing.meta = meta
    else:
        db.session.add(CurrentMetric(
            host_id=host_id,
            oid=oid,
            metric=metric,
            value=value,
            meta=meta
        ))

    db.session.commit()


def open_alert(db, Alert, host_id, severity, message):
    """Crée une alerte si aucune alerte identique n'est déjà ouverte."""
    # Évite la duplication d'alertes identiques (basé sur message)
    existing = Alert.query.filter_by(
        host_id=host_id,
        severity=severity,
        message=message,
        acknowledged_at=None,
        resolved_at=None
    ).first()

    if not existing:
        alert = Alert(
            host_id=host_id,
            severity=severity,
            message=message
        )
        db.session.add(alert)
        db.session.commit()
