# seuils.py
import subprocess
from db_utils import open_alert
from models_extra import CurrentMetric
import platform

_last_status = {}

def check_host_reachability(db, host, Alert):
    """Teste le ping ICMP, compatible Windows/Linux/FR, et génère alertes UP/DOWN."""
    system = platform.system().lower()
    ping_cmd = ["ping", "-n", "1", host.ip] if system == "windows" else ["ping", "-c", "1", host.ip]

    try:
        result = subprocess.run(
            ping_cmd,
            capture_output=True,
            text=True,
            timeout=3,
        )
        output = result.stdout.lower()
        # ✅ On vérifie le contenu du message au lieu du code retour
        is_up = any(kw in output for kw in ["ttl=", "réponse de", "reply from"])
    except Exception as e:
        print(f"[seuils] ⚠️ Erreur ping {host.hostname}: {e}")
        open_alert(db, Alert, host.id, "warning", f"Erreur ping {host.hostname}: {e}")
        return False

    prev = _last_status.get(host.id, "up")

    if not is_up and prev == "up":
        open_alert(db, Alert, host.id, "critical", f"Hôte {host.hostname} injoignable (ping échoué)")
        print(f"[seuils] ❌ Host {host.hostname} unreachable (ping failed)")
        _last_status[host.id] = "down"
        return False

    elif is_up and prev == "down":
        open_alert(db, Alert, host.id, "info", f"Hôte {host.hostname} de nouveau accessible (ping OK)")
        print(f"[seuils] ✅ Host {host.hostname} is back online")
        _last_status[host.id] = "up"

    elif is_up:
        _last_status[host.id] = "up"

    return is_up


def detect_interface_changes(db, host_id, snmp_data, Alert):
    """Détecte les changements d'état d'interface."""
    for oid, val in snmp_data.items():
        if "ifOperStatus" not in oid:
            continue
        prev = CurrentMetric.query.filter_by(host_id=host_id, oid=oid).first()
        if prev and prev.value != val:
            open_alert(db, Alert, host_id, "warning", f"Interface {oid.split('.')[-1]}: {prev.value} → {val}")
            print(f"[seuils] ⚠️ Interface {oid} changed: {prev.value} -> {val}")


def check_thresholds(db, host, category, oid, val, Alert):
    """Vérifie les seuils critiques."""
    try:
        value = float(val)
    except Exception:
        return

    if "cpu" in category.lower():
        if value > 90:
            open_alert(db, Alert, host.id, "critical", f"CPU critique sur {host.hostname} ({value:.1f}%)")
        elif value > 80:
            open_alert(db, Alert, host.id, "warning", f"CPU élevé sur {host.hostname} ({value:.1f}%)")

    if "storage" in category.lower():
        if value > 95:
            open_alert(db, Alert, host.id, "critical", f"Stockage presque plein sur {host.hostname} ({value:.1f}%)")
        elif value > 85:
            open_alert(db, Alert, host.id, "warning", f"Stockage élevé sur {host.hostname} ({value:.1f}%)")
