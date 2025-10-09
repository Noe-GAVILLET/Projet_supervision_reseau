# seuils.py
import subprocess
from db_utils import open_alert
from models_extra import CurrentMetric
import platform

def check_host_reachability(db, host, Alert):
    """
    Vérifie la disponibilité de l’hôte :
      - Si ping OK → True
      - Si ping KO → crée une alerte critique + marque les interfaces comme Down
    """
    system = platform.system().lower()
    cmd = ["ping", "-n", "1", "-w", "2000", host.ip] if system == "windows" else ["ping", "-c", "1", "-W", "2", host.ip]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=True)
        return True  # ✅ Host joignable

    except Exception as e:
        # 🔴 Création d'une alerte critique directe
        msg = f"Hôte {host.hostname} injoignable (ping échoué)"
        open_alert(db, Alert, host.id, "critical", msg)
        print(f"[seuils] ❌ {msg}")

        # 🔻 Marquer les interfaces comme Down
        rows = CurrentMetric.query.filter_by(host_id=host.id).all()
        for r in rows:
            if r.meta == "interfaces":
                r.value = "Down"
        db.session.commit()

        return False


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
