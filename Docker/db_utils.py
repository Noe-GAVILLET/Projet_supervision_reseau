import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from models import CurrentMetric, Measurement, Alert, User
from database import db
import logging
logger = logging.getLogger(__name__)
# ⚠️ Idéalement, lis ces valeurs depuis des variables d'environnement
ADMIN_EMAIL = "noe.gavillet@gmail.com"      # Fallback si aucun abonné
SENDER_EMAIL = "noe.gavillet@gmail.com"     # Compte SMTP utilisé pour l'envoi
APP_PASSWORD = "outjcrsikfnyasim"           # Mot de passe d’application


def _get_alert_recipients() -> list[str]:
    """
    Récupère les emails des utilisateurs actifs qui souhaitent recevoir les alertes.
    Renvoie une liste dédupliquée, nettoyée.
    """
    try:
        users = User.query.filter_by(receive_alerts=True, is_active=True).all()
        emails = {
            (u.email or "").strip().lower()
            for u in users
            if u.email and u.email.strip()
        }
        return sorted(emails)
    except Exception as e:
        print(f"[email] ⚠️ Impossible de récupérer les destinataires: {e}")
        return []


def send_alert_email(subject: str, body: str, to: list[str] | None = None) -> bool:
    """
    Envoie un email d'alerte via Gmail SMTP (TLS 587).
    - to = liste explicite de destinataires (optionnel).
    - Si 'to' n'est pas fourni, on utilise les utilisateurs abonnés (receive_alerts=1).
      S'il n'y en a aucun, fallback sur ADMIN_EMAIL.
    Retourne True si OK, False sinon.
    """
    if not APP_PASSWORD:
        print("[email] ⚠️ Mot de passe d'application manquant.")
        return False

    recipients = to if to is not None else _get_alert_recipients()
    if not recipients:
        # Fallback : on prévient au moins l'admin.
        print("[email] ℹ️ Aucun utilisateur abonné aux alertes — fallback admin.")
        recipients = [ADMIN_EMAIL]

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            # sendmail garantit l'envoi à la liste complète
            server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
            print(f"[email] ✅ Alerte envoyée à: {', '.join(recipients)}")
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
    Crée une alerte si aucune alerte identique (même host, même severité, même message) n'est déjà ouverte,
    puis envoie un e-mail formaté avec hostname + IP.
    """
    from models import Host

    host = Host.query.get(host_id)
    hostname = host.hostname if host else f"Host#{host_id}"
    host_ip = host.ip if host else "IP inconnue"

    # Évite le spam: pas de doublon si même alerte déjà ouverte
    existing = Alert.query.filter_by(
        host_id=host_id,
        severity=severity,
        message=message,
        acknowledged_at=None,
        resolved_at=None
    ).first()
    if existing:
        return existing

    alert = Alert(
        host_id=host_id,
        severity=severity,
        message=message,
        created_at=datetime.utcnow()
    )
    db.session.add(alert)
    db.session.commit()

    print(f"[alerte] 🔔 Nouvelle alerte {severity.upper()} sur {hostname} ({host_ip}) : {message}")

    # ✅ Sujet/texte clairs avec hostname + IP
    subject = f"[{severity.upper()}] {hostname} ({host_ip}) — Alerte SNMP"
    body = (
        "Une nouvelle alerte a été générée :\n\n"
        f"Gravité : {severity.upper()}\n"
        f"Hôte : {hostname} ({host_ip})\n"
        f"Détails : {message}\n"
    )
    # Envoi aux abonnés (ou fallback admin) via la fonction locale
    send_alert_email(subject, body)
    return alert


def resolve_alert(db, Alert, host_id, category=None, message_contains=None):
    """
    Marque comme résolues les alertes ouvertes de ce host (optionnellement filtrées par 'message_contains'),
    puis envoie un e-mail de rétablissement générique (pas “CPU”), avec hostname + IP.
    """
    from models import Host

    host = Host.query.get(host_id)
    hostname = host.hostname if host else f"Host#{host_id}"
    host_ip = host.ip if host else "IP inconnue"

    q = Alert.query.filter(
        Alert.host_id == host_id,
        Alert.resolved_at.is_(None)
    )
    if message_contains:
        q = q.filter(Alert.message.like(f"%{message_contains}%"))

    alerts = q.all()
    if not alerts:
        return

    now = datetime.utcnow()
    for a in alerts:
        a.resolved_at = now
        db.session.add(a)
    db.session.commit()

    # ✅ Mail de rétablissement générique (plus de “Catégorie : CPU” forcée)
    subject = f"[RÉTABLIE] {hostname} ({host_ip}) — Alerte résolue"
    details = "\n".join(f"- {a.severity.upper()} : {a.message}" for a in alerts)
    cat_line = f"Catégorie : {category}\n" if category else ""
    body = (
        "Les alertes suivantes ont été résolues :\n\n"
        f"Hôte : {hostname} ({host_ip})\n"
        f"{cat_line}"
        f"{details}\n\n"
        f"Rétablissement : {now} UTC"
    )
    send_alert_email(subject, body)
    print(f"[alerte] ✅ {len(alerts)} alerte(s) résolue(s) pour host {host_id}")