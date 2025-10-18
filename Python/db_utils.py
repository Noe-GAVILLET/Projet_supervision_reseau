import json
from models import CurrentMetric, Measurement, Alert
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ADMIN_EMAIL = "noe.gavillet@gmail.com"
SENDER_EMAIL = "noe.gavillet@gmail.com"     # Doit correspondre au compte qui possède le mot de passe d’application
APP_PASSWORD = "outjcrsikfnyasim"           # Mot de passe d’application (16 caractères, sans espaces)

def send_alert_email(subject: str, body: str) -> bool:
    """
    Envoie un email d'alerte via Gmail SMTP (TLS 587).
    Retourne True si OK, False sinon.
    """
    if not APP_PASSWORD:
        print("[email] ⚠️ Mot de passe d'application manquant.")
        return False

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = ADMIN_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
            print(f"[email] ✅ Alerte envoyée à {ADMIN_EMAIL}")
            return True
    except Exception as e:
        print(f"[email] ❌ Erreur envoi mail: {e}")
        return False

def upsert_current_metric(db, host_id, oid, metric, value, meta=None):
    """Insère ou met à jour la dernière valeur connue d'une métrique pour un host."""
    if isinstance(meta, (dict, list)):
        meta = json.dumps(meta, ensure_ascii=False)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)

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
    """
    Crée une alerte si aucune alerte identique n'est déjà ouverte,
    puis envoie un mail à l'administrateur.
    """
    existing = Alert.query.filter_by(
        host_id=host_id,
        severity=severity,
        message=message,
        acknowledged_at=None,
        resolved_at=None
    ).first()

    if existing:
        return

    alert = Alert(host_id=host_id, severity=severity, message=message)
    db.session.add(alert)
    db.session.commit()

    print(f"[alerte] 🔔 Nouvelle alerte {severity.upper()} sur host_id={host_id} : {message}")

    subject = f"[{severity.upper()}] Alerte SNMP sur l'hôte {host_id}"
    body = (
        "Une nouvelle alerte a été générée :\n\n"
        f"Gravité : {severity.upper()}\n"
        f"Hôte ID : {host_id}\n"
        f"Détails : {message}\n\n"
    )
    send_alert_email(subject, body)

def resolve_alert(db, Alert, host_id, category, message_contains=None):
    """
    Marque comme résolues les alertes du host pour la catégorie donnée
    si elles ne sont plus valides.
    """
    query = Alert.query.filter(
        Alert.host_id == host_id,
        Alert.resolved_at.is_(None)
    )

    # Filtrer par texte si précisé
    if message_contains:
        query = query.filter(Alert.message.like(f"%{message_contains}%"))

    alerts = query.all()
    if not alerts:
        return

    for alert in alerts:
        alert.resolved_at = datetime.utcnow()
        db.session.add(alert)

        # Envoi d’un mail de rétablissement
        subject = f"[RÉTABLIE] Alerte SNMP sur {category.upper()} - hôte {host_id}"
        body = (
            f"L'alerte suivante a été résolue :\n\n"
            f"Hôte ID : {host_id}\n"
            f"Catégorie : {category.upper()}\n"
            f"Détails : {alert.message}\n\n"
            f"Le service est revenu à la normale à {alert.resolved_at}."
        )
        send_alert_email(subject, body)

    db.session.commit()
    print(f"[alerte] ✅ {len(alerts)} alerte(s) résolue(s) pour {category} sur host {host_id}")
