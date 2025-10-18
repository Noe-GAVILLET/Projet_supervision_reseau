# seuils.py
import subprocess
from db_utils import open_alert, resolve_alert
from models import CurrentMetric, Measurement, Alert
import platform


def check_host_reachability(db, host, Alert, timeout=2):
    """Teste la disponibilité réseau (ping) compatible Windows / Linux."""
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), host.ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), host.ip]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0
    except Exception as e:
        print(f"[reachability] Erreur ping {host.hostname}: {e}")
        return False


def detect_interface_changes(db, host_id, snmp_data, Alert):
    """Détecte les changements d'état d'interface."""
    for oid, val in snmp_data.items():
        if "ifOperStatus" not in oid:
            continue

        prev = CurrentMetric.query.filter_by(host_id=host_id, oid=oid).first()
        if prev and prev.value != val:
            msg = f"Interface {oid.split('.')[-1]}: {prev.value} → {val}"
            open_alert(db, Alert, host_id, severity="warning", message=msg)
            print(f"[seuils] ⚠️ {msg}")


def check_thresholds(db, host, category, oid, val, Alert):
    """Vérifie les seuils critiques et résout les alertes si normalisé."""
    
    try:
        value = float(val)
    except Exception:
        return

    # --- CPU ---
    if "cpu" in category.lower():
        if value > 90:
            open_alert(db, Alert, host.id, "critical", f"CPU critique sur {host.hostname} ({value:.1f}%)")
        elif value > 80:
            open_alert(db, Alert, host.id, "warning", f"CPU élevé sur {host.hostname} ({value:.1f}%)")
        else:
            resolve_alert(db, Alert, host.id, "cpu", "CPU")

    # --- STORAGE ---
    elif "storage" in category.lower():
        if value > 95:
            open_alert(db, Alert, host.id, "critical", f"Stockage presque plein sur {host.hostname} ({value:.1f}%)")
        elif value > 85:
            open_alert(db, Alert, host.id, "warning", f"Stockage élevé sur {host.hostname} ({value:.1f}%)")
        else:
            resolve_alert(db, Alert, host.id, "storage", "Stockage")

    # --- RAM ---
    elif "ram" in category.lower():
        if value > 95:
            open_alert(db, Alert, host.id, "critical", f"RAM critique sur {host.hostname} ({value:.1f}%)")
        elif value > 85:
            open_alert(db, Alert, host.id, "warning", f"RAM élevée sur {host.hostname} ({value:.1f}%)")
        else:
            resolve_alert(db, Alert, host.id, "ram", "RAM")


def get_severity(category: str, value: float) -> str:
    """
    Renvoie 'normal', 'warning' ou 'critical' selon les seuils pour une catégorie.
    """
    if not isinstance(value, (int, float)):
        return "normal"

    cat = category.lower()
    if cat == "cpu":
        if value > 90:
            return "critical"
        elif value > 80:
            return "warning"
    elif cat == "ram":
        if value > 90:
            return "critical"
        elif value > 80:
            return "warning"
    elif cat == "storage":
        if value > 95:
            return "critical"
        elif value > 85:
            return "warning"

    return "normal"
