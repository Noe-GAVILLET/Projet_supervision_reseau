import json
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from models import CurrentMetric, Measurement, Alert, User
from database import db
import logging
logger = logging.getLogger(__name__)
# ⚠️ Idéalement, lis ces valeurs depuis des variables d'environnement
ADMIN_EMAIL = "supervision.alerte.detail@gmail.com"      # Fallback si aucun abonné
SENDER_EMAIL = "supervision.alerte.detail@gmail.com"     # Compte SMTP utilisé pour l'envoi
APP_PASSWORD = "zvkfeqzvkzgfkzes"           # Mot de passe d’application


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
        logger.warning(f"[email] ⚠️ Impossible de récupérer les destinataires: {e}")
        return []


def send_alert_email(subject: str, body: str, to: list[str] | None = None) -> bool:
    """
    Envoie un email d'alerte via Gmail SMTP (TLS 587).
    - to = liste explicite de destinataires (optionnel).
        - Si 'to' n'est pas fourni, on utilise les utilisateurs abonnés (receive_alerts=1).
            S'il n'y en a aucun, on n'envoie aucun mail (pas de fallback admin).
    Retourne True si OK, False sinon.
    """
    if not APP_PASSWORD:
        logger.warning("[email] ⚠️ Mot de passe d'application manquant.")
        return False

    recipients = to if to is not None else _get_alert_recipients()
    if not recipients:
        # Aucun destinataire configuré -> ne pas envoyer de mail du tout
        logger.info("[email] ℹ️ Aucun destinataire configuré pour les alertes — aucun e-mail envoyé.")
        return False
    
    logger.info(f"[email] 📧 Tentative d'envoi d'email à : {recipients}")
    logger.info(f"[email] 📧 Sujet : {subject}")

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
            logger.info(f"[email] ✅ Alerte envoyée à: {', '.join(recipients)}")
            return True
    except Exception as e:
        logger.error(f"[email] ❌ Erreur envoi mail: {e}")
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


def open_alert(db, Alert, host_id, severity, message, cooldown_minutes=10):
    """
    Crée une alerte si aucune alerte identique (même host + même "type" de message)
    n'existe récemment. N'envoie un mail que pour les CRITICAL, et applique un
    cooldown anti-spam (par défaut 10 min) même si l'ancienne alerte est close.
    """
    from models import Host
    host = Host.query.get(host_id)
    hostname = host.hostname if host else f"Host#{host_id}"
    host_ip = host.ip if host else "IP inconnue"

    # 🚫 Pas de mail pour les warnings
    send_email = (severity == "critical")

    # Clé de similarité "douce" : 1er mot du message (ex: "CPU", "RAM", "Stockage", "SNMP")
    # -> garde ton comportement actuel mais un poil plus robuste.
    first_word = (message or "").strip().split()[0] if message else ""
    now = datetime.utcnow()
    since = now - timedelta(minutes=cooldown_minutes)

    # 🔍 1) Si une alerte identique NON RÉSOLUE existe déjà → on ne spam pas
    # Rechercher toute alerte non résolue du même type (même premier mot),
    # indépendamment de la gravité — on la mettra à jour si besoin
    existing_unresolved = (
        Alert.query.filter_by(host_id=host_id)
        .filter(Alert.resolved_at.is_(None))
        .filter(Alert.message.like(f"{first_word}%"))
        .order_by(Alert.created_at.desc())
        .first()
    )
    if existing_unresolved:
        # Si la gravité est identique -> on ne crée rien
        if existing_unresolved.severity == severity:
            logger.debug(f"[alerte] Ignorée (déjà ouverte) : {message}")
            return existing_unresolved
        # Sinon on met à jour l'alerte existante (upgrade/downgrade)
        try:
            old_sev = existing_unresolved.severity
            existing_unresolved.severity = severity
            existing_unresolved.message = message
            # mettre à jour le timestamp pour refléter le changement
            existing_unresolved.created_at = now
            db.session.add(existing_unresolved)
            db.session.commit()
            logger.info(f"[alerte] Mise à jour alerte {old_sev} -> {severity} pour host {host_id}: {message}")
            # Si on monte en CRITICAL et que l'envoi est autorisé, on envoie un mail
            if send_email and severity == "critical":
                subject = f"[CRITICAL] {hostname} ({host_ip}) — Alerte SNMP"
                body = (
                    f"Une alerte critique a été détectée :\n\n"
                    f"Hôte : {hostname} ({host_ip})\n"
                    f"Gravité : {severity.upper()}\n"
                    f"Détails : {message}\n"
                )
                send_alert_email(subject, body)
            # Mettre à jour le statut de l'hôte si nécessaire (sauf si déjà DOWN)
            try:
                if host and getattr(host, 'status', None) != 'down' and severity in ('warning', 'critical'):
                    host.status = 'warning'
                    host.last_status_change = now
                    db.session.add(host)
                    db.session.commit()
            except Exception:
                logger.exception("Erreur lors de la mise à jour du statut d'hôte après mise à jour d'alerte")
            return existing_unresolved
        except Exception as e:
            logger.exception(f"[alerte] Erreur mise à jour alerte existante: {e}")
            # Si mise à jour échoue, on continue et laisse la logique créer une nouvelle alerte

    # ⏳ 2) Cooldown : si une alerte similaire a été créée récemment (même type, même severité)
    #    on recrée l'alerte pour l'historique uniquement si tu le souhaites, mais SANS mail.
    last_similar = (
        Alert.query.filter_by(host_id=host_id, severity=severity)
        .filter(Alert.message.like(f"{first_word}%"))
        .order_by(Alert.created_at.desc())
        .first()
    )
    if last_similar and last_similar.created_at >= since:
        # Cooldown actif → on réutilise / rouvre l'alerte existante au lieu d'en créer une nouvelle
        try:
            send_email = False
            logger.info(f"[alerte] ⏱️ Cooldown actif ({cooldown_minutes} min) pour {hostname} – mise à jour de l'alerte existante.")
            # Ré-ouvrir l'alerte si elle était résolue récemment
            last_similar.message = message
            last_similar.severity = severity
            last_similar.created_at = now
            last_similar.resolved_at = None
            db.session.add(last_similar)
            db.session.commit()
            # Mettre à jour le statut de l'hôte si nécessaire (sauf si déjà DOWN)
            try:
                if host and getattr(host, 'status', None) != 'down' and severity in ('warning', 'critical'):
                    host.status = 'warning'
                    host.last_status_change = now
                    db.session.add(host)
                    db.session.commit()
            except Exception:
                logger.exception("Erreur lors de la mise à jour du statut d'hôte après réouverture d'alerte")
            return last_similar
        except Exception as e:
            logger.exception(f"[alerte] Erreur lors de la réutilisation d'une alerte existante: {e}")
            # en cas d'erreur on continue et on laisse la logique créer une nouvelle alerte

    # ✅ 3) Création de la nouvelle alerte (on conserve l'historique dans /alerts)
    alert = Alert(
        host_id=host_id,
        severity=severity,
        message=message,
        created_at=now
    )
    db.session.add(alert)
    db.session.commit()

    print(f"[alerte] 🔔 Nouvelle alerte {severity.upper()} sur {hostname} ({host_ip}) : {message}")

    # 📧 4) Envoi e-mail uniquement pour CRITICAL, et si cooldown non actif
    if send_email and severity == "critical":
        subject = f"[CRITICAL] {hostname} ({host_ip}) — Alerte SNMP"
        body = (
            f"Une alerte critique a été détectée :\n\n"
            f"Hôte : {hostname} ({host_ip})\n"
            f"Gravité : {severity.upper()}\n"
            f"Détails : {message}\n"
        )
        send_alert_email(subject, body)

    # Mettre à jour le statut d'hôte : si l'hôte n'est pas DOWN, le passer en WARNING
    try:
        if host and getattr(host, 'status', None) != 'down' and severity in ('warning', 'critical'):
            host.status = 'warning'
            host.last_status_change = now
            db.session.add(host)
            db.session.commit()
    except Exception:
        logger.exception("Erreur lors de la mise à jour du statut d'hôte après création d'alerte")

    return alert


def resolve_alert(db, Alert, host_id, category=None, message_contains=None, min_age_seconds=5, force=False):
    """
    Marque comme résolues les alertes ouvertes pour ce host (optionnellement filtrées),
    puis envoie un e-mail de rétablissement uniquement si une alerte critique était concernée.

    Pour éviter les bascules immédiates (alerte ouverte puis résolue dans la même passe),
    la fonction ignore par défaut les alertes créées il y a moins de `min_age_seconds`.
    Passe `force=True` pour forcer la résolution immédiate.
    """
    from models import Host
    host = Host.query.get(host_id)
    hostname = host.hostname if host else f"Host#{host_id}"
    host_ip = host.ip if host else "IP inconnue"

    now = datetime.utcnow()

    logger.debug(f"[alerte] resolve_alert called for host={host_id} category={category} filter={message_contains} force={force}")

    q = Alert.query.filter(
        Alert.host_id == host_id,
        Alert.resolved_at.is_(None)
    )
    if message_contains:
        # Use a conservative starts-with match to avoid resolving unrelated alerts
        pattern = f"{message_contains}%"
        try:
            q = q.filter(Alert.message.ilike(pattern))
        except Exception:
            # Fallback if ilike not available in this dialect
            q = q.filter(Alert.message.like(pattern))

    # Exclure les alertes très récentes pour éviter de résoudre une alerte qui vient d'être créée
    if not force and min_age_seconds and min_age_seconds > 0:
        cutoff = now - timedelta(seconds=min_age_seconds)
        q = q.filter(Alert.created_at <= cutoff)

    alerts = q.all()
    if not alerts:
        # if no alerts found with the provided strict filter, optionally try a broader SNMP-related fallback
        if message_contains and ("snmp" in (message_contains or "").lower() or (category and str(category).lower() == "snmp")):
            try:
                alt_q = Alert.query.filter(
                    Alert.host_id == host_id,
                    Alert.resolved_at.is_(None)
                ).filter(
                    (Alert.message.ilike(f"%{message_contains}%")) | (Alert.message.ilike(f"%SNMP%"))
                )
                alerts = alt_q.all()
            except Exception:
                alerts = []
        if not alerts:
            logger.debug(f"[alerte] Aucun alert trouvé pour host={host_id} filter={message_contains}")
            return

    resolved_time = datetime.utcnow()
    severities = {a.severity for a in alerts}

    resolved_ids = []
    for a in alerts:
        a.resolved_at = resolved_time
        db.session.add(a)
        resolved_ids.append(a.id)
    try:
        db.session.commit()
    except Exception:
        logger.exception("Erreur commit lors de la résolution d'alertes")
        db.session.rollback()
        return

    logger.info(f"[alerte] Résolution d'alertes pour host {host_id} : ids={resolved_ids}")

    print(f"[alerte] ✅ {len(alerts)} alerte(s) résolue(s) pour host {host_id}")

    # 📧 Envoi mail uniquement si une alerte critique était concernée
    if "critical" in severities:
        subject = f"[RÉTABLIE] {hostname} ({host_ip}) — Alerte critique résolue"
        details = "\n".join(f"- {a.severity.upper()} : {a.message}" for a in alerts)
        cat_line = f"Catégorie : {category}\n" if category else ""
        body = (
            f"Les alertes suivantes ont été résolues :\n\n"
            f"Hôte : {hostname} ({host_ip})\n"
            f"{cat_line}"
            f"{details}\n\n"
            f"Rétablissement : {resolved_time} UTC"
        )
        send_alert_email(subject, body)

    # Si aucune alerte non résolue ne reste pour cet hôte, remettre le statut à 'up'
    try:
        remaining = Alert.query.filter(Alert.host_id == host_id, Alert.resolved_at.is_(None)).count()
        if remaining == 0 and host:
            host.status = 'up'
            host.last_status_change = resolved_time
            db.session.add(host)
            db.session.commit()
    except Exception:
        logger.exception("Erreur lors de la remise à jour du statut d'hôte après résolution d'alertes")


def resolve_snmp_alerts(db, Alert, host_id, min_age_seconds=0, force=False):
    """
    Résout explicitement les alertes liées à SNMP pour un hôte donné.
    Cette fonction cherche les messages contenant 'SNMP' ou 'injoignable' (insensible
    à la casse) et les marque résolues. Elle est destinée à être appelée
    lorsque le poller détecte que SNMP est de nouveau joignable.
    """
    from models import Host
    host = Host.query.get(host_id)
    hostname = host.hostname if host else f"Host#{host_id}"
    host_ip = host.ip if host else "IP inconnue"

    try:
        q = Alert.query.filter(Alert.host_id == host_id, Alert.resolved_at.is_(None)).filter(
            (Alert.message.ilike("%SNMP%")) | (Alert.message.ilike("%injoignable%"))
        )
        alerts = q.all()
    except Exception:
        logger.exception("Erreur lecture alertes SNMP pour résolution")
        alerts = []

    if not alerts:
        logger.debug(f"[alerte] Pas d'alertes SNMP ouvertes pour host={host_id}")
        return

    resolved_time = datetime.utcnow()
    resolved_ids = []
    severities = {a.severity for a in alerts}

    for a in alerts:
        a.resolved_at = resolved_time
        db.session.add(a)
        resolved_ids.append(a.id)

    try:
        db.session.commit()
    except Exception:
        logger.exception("Erreur commit lors de la résolution d'alertes SNMP")
        db.session.rollback()
        return

    logger.info(f"[alerte] Résolution SNMP pour host {host_id} : ids={resolved_ids}")

    # Envoi mail si une alerte critique faisait partie du lot
    if "critical" in severities:
        subject = f"[RÉTABLIE] {hostname} ({host_ip}) — Alerte SNMP résolue"
        details = "\n".join(f"- {a.severity.upper()} : {a.message}" for a in alerts)
        body = (
            f"Les alertes SNMP suivantes ont été résolues :\n\n"
            f"Hôte : {hostname} ({host_ip})\n"
            f"{details}\n\n"
            f"Rétablissement : {resolved_time} UTC"
        )
        send_alert_email(subject, body)

    # Remise à 'up' si aucune alerte non résolue ne reste
    try:
        remaining = Alert.query.filter(Alert.host_id == host_id, Alert.resolved_at.is_(None)).count()
        if remaining == 0 and host:
            host.status = 'up'
            host.last_status_change = resolved_time
            db.session.add(host)
            db.session.commit()
    except Exception:
        logger.exception("Erreur lors de la remise à jour du statut d'hôte après résolution d'alertes SNMP")