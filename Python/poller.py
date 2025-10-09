import time
import threading
from snmp_utils import get_metrics
from db_utils import upsert_current_metric, open_alert
from seuils import check_host_reachability, detect_interface_changes, check_thresholds
from models_extra import CurrentMetric

# Cache mémoire des statuts connus
HOST_STATUS_CACHE = {}

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

            # 🔹 Test ping à chaque cycle (valeur réelle)
            reachable = check_host_reachability(db, host, Alert)

            # --- 🔴 DOWN ---
            if not reachable:
                if previous_status == "down":
                    # On vérifie si cela fait trop longtemps (sécurité)
                    print(f"[poller] 🔴 {hostname} toujours DOWN (aucune nouvelle alerte)")
                    continue

                HOST_STATUS_CACHE[host_id] = "down"
                open_alert(db, Alert, host_id, "critical",
                           f"Hôte {hostname} injoignable (ping échoué)")
                print(f"[poller] ❌ Host {hostname} DOWN (nouvelle alerte critique)")
                continue

            # --- 🟢 UP ---
            if previous_status == "down":
                # Transition DOWN -> UP
                HOST_STATUS_CACHE[host_id] = "up"
                open_alert(db, Alert, host_id, "info",
                           f"Hôte {hostname} est de nouveau joignable ✅")
                print(f"[poller] ✅ Host {hostname} back UP")
            else:
                # Correction auto si cache désynchronisé
                if previous_status != "up":
                    print(f"[poller] 🔄 Sync: host {hostname} détecté UP (cache réparé)")
                HOST_STATUS_CACHE[host_id] = "up"

            # --- SNMP Poll ---
            try:
                for cat in (host.snmp_categories or []):
                    data = get_metrics(host.ip, host.snmp_community, host.port, cat)

                    if cat == "interfaces":
                        detect_interface_changes(db, host.id, data, Alert)

                    for oid, val in data.items():
                        upsert_current_metric(db, host.id, oid, oid, val, meta=cat)
                        check_thresholds(db, host, cat, oid, val, Alert)

                print(f"[poller] ✅ Metrics updated for {hostname}")

            except Exception as e:
                print(f"[poller] ⚠️ Error polling {hostname}: {e}")
                open_alert(db, Alert, host_id, "warning",
                           f"SNMP timeout or host unreachable: {e}")


def start_scheduler(app, db, Host, Alert):
    """Démarre le scheduler SNMP en thread séparé (toutes les 15 secondes)."""
    print("[poller] SNMP scheduler started (15s interval)")

    def loop():
        while True:
            poll_host_metrics(app, db, Host, Alert)
            time.sleep(15)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
