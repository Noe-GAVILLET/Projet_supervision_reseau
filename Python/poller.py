import time
import threading
import json
from datetime import datetime
from snmp_utils import get_metrics
from db_utils import upsert_current_metric, open_alert, resolve_alert
from seuils import check_host_reachability, detect_interface_changes, check_thresholds
from models import CurrentMetric, Measurement, Alert

# Cache mémoire des statuts connus
HOST_STATUS_CACHE = {}

SNMP_DOWN_MSG = "SNMP injoignable (timeout)"
SNMP_UP_MSG = "SNMP rétabli ✅"


# ==============================================================
# 🔹 LOGGER STANDARDISÉ
# ==============================================================
def log_poller(level: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [poller] {level} {message}")


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
            snmp_ok = True
            if ping_ok and categories:
                for cat in categories:
                    try:
                        data = get_metrics(host.ip, host.snmp_community, host.port, cat)
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

                    except Exception:
                        snmp_ok = False
                        break  # un seul échec SNMP → on arrête les autres catégories

            # 3️⃣ Statut global simplifié
            new_status = "down" if (not ping_ok or not snmp_ok) else "up"

            # 4️⃣ Changement d’état
            if new_status != previous_status:
                HOST_STATUS_CACHE[host_id] = new_status
                host.status = new_status
                db.session.commit()

                if new_status == "down":
                    open_alert(db, Alert, host_id, "critical",
                               f"{SNMP_DOWN_MSG} sur {hostname} ({host.ip})")
                    log_poller("❌", f"{hostname} DOWN (ping ou SNMP KO) [{host.ip}]")
                else:
                    resolve_alert(db, Alert, host_id, category="SNMP", message_contains="injoignable")

                    # 📨 Alerte d'information (rétablissement)
                    open_alert(db, Alert, host_id, "info",
                            f"{SNMP_UP_MSG} sur {hostname} ({host.ip})")

                    log_poller("✅", f"Host {hostname} back UP [{host.ip}]")

            # 5️⃣ Résumé final par hôte
            if new_status == "up":
                log_poller("✅", f"Metrics updated for {hostname} [{host.ip}]")
            else:
                log_poller("❌", f"Host {hostname} DOWN — métriques non mises à jour")

            db.session.commit()

        # Résumé global
        up = sum(1 for s in HOST_STATUS_CACHE.values() if s == "up")
        down = sum(1 for s in HOST_STATUS_CACHE.values() if s == "down")
        log_poller("📊", f"Scan terminé — {up} UP, {down} DOWN")


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
