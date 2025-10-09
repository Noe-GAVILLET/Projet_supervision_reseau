import time
import threading
from snmp_utils import get_metrics
from db_utils import upsert_current_metric, open_alert
from seuils import check_host_reachability, detect_interface_changes, check_thresholds


def poll_host_metrics(app, db, Host, Alert):
    """Effectue le poll SNMP sur tous les hôtes enregistrés."""
    with app.app_context():
        hosts = Host.query.all()
        print(f"[poller] Scanning {len(hosts)} hosts...")

        for host in hosts:
            # 🔹 1. Vérifie disponibilité avant SNMP
            if not check_host_reachability(db, host, Alert):
                continue

            try:
                for cat in (host.snmp_categories or []):
                    data = get_metrics(host.ip, host.snmp_community, host.port, cat)

                    # 🔹 2. Détection interfaces
                    if cat == "interfaces":
                        detect_interface_changes(db, host.id, data, Alert)

                    # 🔹 3. Seuils automatiques
                    for oid, val in data.items():
                        upsert_current_metric(db, host.id, oid, oid, val, meta=cat)
                        check_thresholds(db, host, cat, oid, val, Alert)

                print(f"[poller] ✅ Metrics updated for {host.hostname}")

            except Exception as e:
                print(f"[poller] ⚠️ Error polling {host.hostname}: {e}")
                open_alert(db, Alert, host.id, "warning", f"SNMP timeout or host unreachable: {e}")


def start_scheduler(app, db, Host, Alert):
    """Démarre le scheduler SNMP en thread séparé (toutes les 15 secondes)."""
    print("[poller] SNMP scheduler started (15s interval)")

    def loop():
        while True:
            poll_host_metrics(app, db, Host, Alert)
            time.sleep(15)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
