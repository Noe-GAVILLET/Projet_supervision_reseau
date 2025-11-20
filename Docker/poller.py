import time
import threading
import json
from datetime import datetime
from snmp_utils import get_metrics
from db_utils import upsert_current_metric, open_alert, resolve_alert, resolve_snmp_alerts
from seuils import check_host_reachability, detect_interface_changes, check_thresholds
from models import CurrentMetric, Measurement, Alert
import logging
poller_logger = logging.getLogger(__name__)

# Cache mémoire des statuts connus
HOST_STATUS_CACHE = {}

SNMP_DOWN_MSG = "SNMP injoignable (timeout)"
SNMP_UP_MSG = "SNMP rétabli ✅"


# ==============================================================
# 🔹 LOGGER STANDARDISÉ
# ==============================================================
def log_poller(icon: str, message: str):
    """
    Écrit les logs dans poller.log et dans la console avec le format habituel.
    Exemple : log_poller("📡", "Scanning 2 hosts...")
    """
    formatted = f"{icon} {message}"
    poller_logger.info(formatted)


def _normalize_categories(raw):
    """Normalize snmp_categories stored as list or JSON string."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, (list, tuple)):
                return list(parsed)
        except Exception:
            return [c.strip() for c in raw.split(",") if c.strip()]
    return []


# ==============================================================
# 🔹 POLL PRINCIPAL
# ==============================================================
def poll_host_metrics(app, db, Host, Alert):
    global HOST_STATUS_CACHE

    with app.app_context():
        hosts = Host.query.all()
        log_poller("📡", f"Scanning {len(hosts)} hosts...")

        current_ids = {h.id for h in hosts}
        for cached_id in list(HOST_STATUS_CACHE.keys()):
            if cached_id not in current_ids:
                HOST_STATUS_CACHE.pop(cached_id, None)
                log_poller("🗑️", f" Host ID {cached_id} supprimé du cache (n’existe plus en BDD)")

        for host in hosts:
            host_id = host.id
            hostname = host.hostname
            categories = _normalize_categories(host.snmp_categories)
            previous_status = HOST_STATUS_CACHE.get(host_id, host.status or "unknown")
            HOST_STATUS_CACHE[host_id] = previous_status

            # 1️⃣ Vérif Ping
            try:
                ping_ok = check_host_reachability(db, host, Alert)
            except Exception as e:
                log_poller("⚠️", f"Erreur reachability pour {hostname}: {e}")
                open_alert(db, Alert, host_id, "critical", f"Erreur reachability: {e}")
                ping_ok = False

            # 2️⃣ SNMP
            # Tentative SNMP indépendante du ping : on considère SNMP OK si au moins
            # une catégorie renvoie des données valides. Si l'hôte n'a pas de
            # catégories SNMP configurées, on considère SNMP OK (rien à collecter).
            snmp_ok = True if not categories else False
            if categories:
                for cat in categories:
                    try:
                        data = get_metrics(host.ip, host.snmp_community, host.port, cat)
                        # Si on obtient des données, marque SNMP comme OK
                        if data:
                            snmp_ok = True

                        if cat == "interfaces":
                            detect_interface_changes(db, host.id, data, Alert)

                        for oid, val in (data.items() if isinstance(data, dict) else []):
                            try:
                                upsert_current_metric(db, host.id, oid, oid, val, meta=cat)
                                check_thresholds(db, host, cat, oid, val, Alert)
                            except Exception as e_sub:
                                log_poller("⚠️", f"{hostname} ({cat}/{oid}) erreur : {e_sub}")

                            if isinstance(val, dict):
                                for sub_key, sub_val in val.items():
                                    db.session.add(Measurement(
                                        host_id=host.id,
                                        oid=f"{oid}.{sub_key}",
                                        metric=sub_key,
                                        value=str(sub_val),
                                        meta=cat
                                    ))
                            else:
                                db.session.add(Measurement(
                                    host_id=host.id,
                                    oid=oid,
                                    metric=oid,
                                    value=str(val),
                                    meta=cat
                                ))

                    except Exception as e:
                        # ne pas breaker : tenter les autres catégories — une seule
                        # catégorie réussie suffit pour considérer SNMP OK
                        log_poller("⚠️", f"{hostname} ({cat}) SNMP erreur: {e}")
                        continue

            # 3️⃣ Statut global simplifié
            # Déterminer le statut en se basant sur SNMP (down si SNMP KO).
            # Si SNMP OK, vérifier s'il existe des alertes warning/critical non résolues
            # pour promouvoir en 'warning'.
            log_poller("🔍", f"host={hostname} ping_ok={ping_ok} snmp_ok={snmp_ok} prev={previous_status}")
            try:
                if snmp_ok:
                    # Si SNMP est joignable, tenter de résoudre toute alerte SNMP en attente
                    try:
                        resolve_snmp_alerts(db, Alert, host_id, force=True)
                    except Exception as e:
                        log_poller("⚠️", f"Erreur lors de tentative de résolution SNMP pour {hostname}: {e}")

                    active_problem = Alert.query.filter(
                        Alert.host_id == host.id,
                        Alert.resolved_at.is_(None),
                        Alert.severity.in_(["warning", "critical"])
                    ).count()
                    new_status = "warning" if active_problem and active_problem > 0 else "up"
                else:
                    # SNMP KO → host down
                    active_problem = Alert.query.filter(
                        Alert.host_id == host.id,
                        Alert.resolved_at.is_(None),
                        Alert.severity.in_(["warning", "critical"])
                    ).count()
                    new_status = "down"
            except Exception as e:
                log_poller("⚠️", f"Erreur lecture alertes pour host {hostname}: {e}")
                # En cas d'erreur, conserver le statut précédent
                new_status = previous_status
            if not host.last_status_change:
                host.last_status_change = datetime.utcnow()

            # Si des alertes non résolues de type warning/critical existent pour cet hôte,
            # elles doivent avoir la priorité sur 'up'. Ordre de priorité : down > warning > up.
            # (active_problem is set above)

            # 4️⃣ Changement d’état
            if new_status != previous_status:
                log_poller("ℹ️", f"host={hostname} status change {previous_status} -> {new_status} (snmp_ok={snmp_ok} active_problem={active_problem})")
                HOST_STATUS_CACHE[host_id] = new_status
                host.status = new_status

                # 🕓 Nouveau : enregistrer l’heure du changement d’état
                host.last_status_change = datetime.utcnow()

                db.session.commit()

                if new_status == "down":
                    open_alert(db, Alert, host_id, "critical",
                            f"{SNMP_DOWN_MSG} sur {hostname} ({host.ip})")
                    log_poller("❌", f"{hostname} DOWN (ping ou SNMP KO) [{host.ip}]")

                elif new_status == "up":
                    # Force immediate resolution for SNMP reachability alerts
                    # Résolution robuste des alertes SNMP : utilise la fonction dédiée
                    try:
                        resolve_snmp_alerts(db, Alert, host_id, force=True)
                    except Exception as e:
                        log_poller("⚠️", f"Erreur lors de la résolution d'alertes SNMP pour {hostname}: {e}")

                    # 🔹 Cas 1 : Unknown → Up → première connexion, pas de mail
                    if previous_status == "unknown":
                        alert = Alert(
                            host_id=host_id,
                            severity="info",
                            message=f"Connexion SNMP établie avec succès sur {hostname} ({host.ip})",
                            created_at=datetime.utcnow()
                        )
                        db.session.add(alert)
                        db.session.commit()
                        log_poller("🟢", f"{hostname} ajouté avec succès [{host.ip}] (première détection)")

                    # 🔹 Cas 2 : Down → Up → vraie reprise → mail envoyé
                    # Ne créer l'alerte "SNMP rétabli" que si le statut précédent était "down"
                    elif previous_status == "down":
                        open_alert(db, Alert, host_id, "info",
                                f"{SNMP_UP_MSG} sur {hostname} ({host.ip})")
                        log_poller("✅", f"Host {hostname} back UP [{host.ip}]")


            # 5️⃣ Résumé final par hôte (traiter explicitement 'warning')
            if new_status == "up":
                log_poller("✅", f"Metrics updated for {hostname} [{host.ip}]")
            elif new_status == "warning":
                log_poller("⚠️", f"Host {hostname} WARNING — métriques partiellement dégradées [{host.ip}]")
            else:
                log_poller("❌", f"Host {hostname} DOWN — métriques non mises à jour")

            db.session.commit()

    # Résumé global
    up = sum(1 for s in HOST_STATUS_CACHE.values() if s == "up")
    warning = sum(1 for s in HOST_STATUS_CACHE.values() if s == "warning")
    down = sum(1 for s in HOST_STATUS_CACHE.values() if s == "down")
    log_poller("📊", f"Scan terminé — {up} UP, {warning} WARNING, {down} DOWN")
    # Dump du cache complet pour debug
    try:
        cache_snapshot = ", ".join(f"{k}:{v}" for k, v in HOST_STATUS_CACHE.items())
        log_poller("📚", f"HOST_STATUS_CACHE: {cache_snapshot}")
    except Exception:
        pass


# ==============================================================
# 🔹 SCHEDULER ROBUSTE
# ==============================================================
_scheduler_started = False

def start_scheduler(app, db, Host, Alert):
    """Démarre le scheduler SNMP en thread séparé (toutes les 15 secondes)."""
    global _scheduler_started
    if _scheduler_started:
        log_poller("⚪", "Scheduler déjà en cours — démarrage ignoré (évite doublons Flask debug).")
        return

    _scheduler_started = True
    log_poller("🚀", "SNMP scheduler started (15s interval)")

    def loop():
        while True:
            try:
                poll_host_metrics(app, db, Host, Alert)
            except Exception as e:
                log_poller("💥", f"Erreur dans poll_host_metrics(): {e}")
            time.sleep(15)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
