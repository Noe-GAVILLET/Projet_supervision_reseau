# seuils.py
import subprocess
from db_utils import open_alert
from models import CurrentMetric, Measurement, Alert
import platform


def check_host_reachability(db, host, Alert):
    """
    Vérifie la disponibilité de l’hôte :
      - Si ping OK → True
      - Si ping KO → crée une alerte critique (si pas déjà ouverte) + marque les interfaces Down
    """
    import platform
    import subprocess

    system = platform.system().lower()
    cmd = ["ping", "-n", "1", "-w", "2000", host.ip] if system == "windows" else ["ping", "-c", "1", "-W", "2", host.ip]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=True)
        return True  # ✅ Hôte joignable

    except Exception:
        # ⚠️ Si une alerte ping est déjà ouverte, ne pas en recréer
        msg = f"Hôte {host.hostname} injoignable (ping échoué)"
        existing = Alert.query.filter_by(host_id=host.id, severity="critical", message=msg, is_closed=False).first()

        if not existing:
            open_alert(db, Alert, host.id, severity="critical", message=msg)
            print(f"[seuils] ❌ {msg}")
        else:
            print(f"[seuils] 🔁 Alerte ping déjà ouverte pour {host.hostname}, aucune nouvelle alerte.")

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
            msg = f"Interface {oid.split('.')[-1]}: {prev.value} → {val}"
            open_alert(db, Alert, host_id, severity="warning", message=msg)
            print(f"[seuils] ⚠️ {msg}")


def check_thresholds(db, host, category, oid, val, Alert):
    """Vérifie les seuils critiques."""
    try:
        value = float(val)
    except Exception:
        return

    # --- CPU ---
    if "cpu" in category.lower():
        if value > 90:
            open_alert(db, Alert, host.id, severity="critical",
                       message=f"CPU critique sur {host.hostname} ({value:.1f}%)")
        elif value > 80:
            open_alert(db, Alert, host.id, severity="warning",
                       message=f"CPU élevé sur {host.hostname} ({value:.1f}%)")

    # --- STORAGE ---
    if "storage" in category.lower():
        if value > 95:
            open_alert(db, Alert, host.id, severity="critical",
                       message=f"Stockage presque plein sur {host.hostname} ({value:.1f}%)")
        elif value > 85:
            open_alert(db, Alert, host.id, severity="warning",
                       message=f"Stockage élevé sur {host.hostname} ({value:.1f}%)")
