# poller.py
import time
import threading
import json
from datetime import datetime
from snmp_utils import get_metrics
from db_utils import upsert_current_metric, open_alert
from seuils import check_host_reachability, detect_interface_changes, check_thresholds
from models import CurrentMetric, Measurement, Alert

# Cache mémoire des statuts connus
HOST_STATUS_CACHE = {}


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


def poll_host_metrics(app, db, Host, Alert):
    """Effectue le poll SNMP sur tous les hôtes enregistrés."""
    global HOST_STATUS_CACHE

    with app.app_context():
        hosts = Host.query.all()
        print(f"[poller] Scanning {len(hosts)} hosts...")

        for host in hosts:
            host_id = host.id
            hostname = host.hostname
            previous_status = HOST_STATUS_CACHE.get(host_id, "unknown")

            categories = _normalize_categories(host.snmp_categories)

            # 🔹 Test ping
            try:
                reachable = check_host_reachability(db, host, Alert)
            except Exception as e:
                print(f"[poller] ⚠️ Erreur reachability pour {hostname}: {e}")
                open_alert(db, Alert, host_id, "warning", f"Erreur reachability: {e}")
                reachable = False

            # --- 🔴 DOWN ---
            if not reachable:
                if previous_status == "down":
                    print(f"[poller] 🔴 {hostname} toujours DOWN (aucune nouvelle alerte)")
                    continue

                HOST_STATUS_CACHE[host_id] = "down"
                print(f"[poller] ❌ Host {hostname} DOWN")
                # L'alerte critique est déjà créée dans check_host_reachability
                continue

            # --- 🟢 UP ---
            if previous_status == "down":
                HOST_STATUS_CACHE[host_id] = "up"

                # ✅ Marquer les anciennes alertes ping comme résolues
                old_alerts = (
                    Alert.query.filter(
                        Alert.host_id == host_id,
                        Alert.severity == "critical",
                        Alert.message.like("%ping échoué%"),
                        Alert.resolved_at.is_(None)
                    ).all()
                )
                for a in old_alerts:
                    a.resolved_at = datetime.utcnow()

                # ✅ Créer une nouvelle alerte info
                open_alert(db, Alert, host_id, "info", f"Hôte {hostname} est de nouveau joignable ✅")

                db.session.commit()
                print(f"[poller] ✅ Host {hostname} back UP")
            else:
                if previous_status != "up":
                    print(f"[poller] 🔄 Sync: host {hostname} détecté UP (cache réparé)")
                HOST_STATUS_CACHE[host_id] = "up"

            # --- SNMP Poll ---
            try:
                if not categories:
                    print(f"[poller] ⚪ Host {hostname} : pas de catégories SNMP configurées.")
                    continue

                if HOST_STATUS_CACHE.get(host_id) != "up":
                    print(f"[poller] ⏭️ Host {hostname} marqué DOWN — SNMP SKIPPED")
                    continue

                for cat in categories:
                    if HOST_STATUS_CACHE.get(host_id) != "up":
                        print(f"[poller] ⏭️ {hostname}: SNMP {cat} ignoré (host DOWN)")
                        break

                    try:
                        data = get_metrics(host.ip, host.snmp_community, host.port, cat)
                    except Exception as e_cat:
                        if HOST_STATUS_CACHE.get(host_id) == "down":
                            print(f"[poller] 🚫 Ignoring SNMP error for DOWN host {hostname} ({cat})")
                            continue

                        print(f"[poller] ⚠️ Erreur SNMP {hostname} ({cat}): {e_cat}")
                        open_alert(db, Alert, host_id, "warning", f"Erreur SNMP ({cat}): {e_cat}")
                        continue

                    if cat == "interfaces":
                        try:
                            detect_interface_changes(db, host.id, data, Alert)
                        except Exception as e_det:
                            print(f"[poller] ⚠️ detect_interface_changes failed for {hostname}: {e_det}")

                    for oid, val in (data.items() if isinstance(data, dict) else []):
                        try:
                            upsert_current_metric(db, host.id, oid, oid, val, meta=cat)
                        except Exception as e_up:
                            print(f"[poller] ⚠️ upsert_current_metric failed ({hostname} {oid}): {e_up}")

                        try:
                            check_thresholds(db, host, cat, oid, val, Alert)
                        except Exception as e_thr:
                            print(f"[poller] ⚠️ check_thresholds failed ({hostname} {oid}): {e_thr}")

                        if isinstance(val, dict):
                            for sub_key, sub_val in val.items():
                                meas = Measurement(
                                    host_id=host.id,
                                    oid=f"{oid}.{sub_key}",
                                    metric=sub_key,
                                    value=str(sub_val),
                                    meta=cat
                                )
                                db.session.add(meas)
                        else:
                            meas = Measurement(
                                host_id=host.id,
                                oid=oid,
                                metric=oid,
                                value=str(val),
                                meta=cat
                            )
                            db.session.add(meas)

                db.session.commit()
                print(f"[poller] ✅ Metrics updated for {hostname}")

            except Exception as e:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                print(f"[poller] ⚠️ Error polling {hostname}: {e}")
                try:
                    open_alert(db, Alert, host_id, "warning",
                               f"SNMP timeout or host unreachable: {e}")
                except Exception as e2:
                    print(f"[poller] ⚠️ open_alert failed: {e2}")


def start_scheduler(app, db, Host, Alert):
    """Démarre le scheduler SNMP en thread séparé (toutes les 15 secondes)."""
    print("[poller] SNMP scheduler started (15s interval)")

    def loop():
        while True:
            poll_host_metrics(app, db, Host, Alert)
            time.sleep(15)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
