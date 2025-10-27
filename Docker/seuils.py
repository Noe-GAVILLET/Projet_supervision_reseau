import subprocess
import platform
import logging
from db_utils import open_alert, resolve_alert
from models import CurrentMetric, Measurement, Alert

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Vérification de la disponibilité réseau (ping)
# ---------------------------------------------------------------
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


# ---------------------------------------------------------------
# Détection des changements d'état d'interface
# ---------------------------------------------------------------
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

# ---------------------------------------------------------------
# Vérification des seuils (CPU / RAM / STORAGE)
# ---------------------------------------------------------------
def check_thresholds(db, host, category, oid, val, Alert):
    """Vérifie les seuils personnalisés de l’hôte (sinon valeurs par défaut)."""
    
    if category.lower() not in ["cpu", "ram", "storage"]:
        return
    # 🔹 Extraction propre du pourcentage selon le type de valeur
    try:
        if isinstance(val, dict):
            # Cas RAM / STORAGE avec structure {"used": ..., "total": ..., "pct": ...}
            value = float(val.get("pct", 0))
        else:
            value = float(val)
    except Exception:
        return

    cat = category.lower()

    # 🔸 Seuils par défaut (fallback)
    default_thresholds = {
        "cpu": {"warning": 80, "critical": 90},
        "ram": {"warning": 85, "critical": 95},
        "storage": {"warning": 85, "critical": 95},
    }

    # 🔹 Seuils personnalisés si présents
    thresholds = default_thresholds.get(cat, {"warning": 80, "critical": 90})
    if getattr(host, "thresholds", None) and isinstance(host.thresholds, dict):
        custom = host.thresholds.get(cat)
        if custom and isinstance(custom, dict):
            thresholds.update({
                k: float(v) for k, v in custom.items() if isinstance(v, (int, float))
            })

    warn = thresholds.get("warning", 80)
    crit = thresholds.get("critical", 90)

    # 🔹 Application des seuils
    if value >= crit:
        open_alert(db, Alert, host.id, "critical", f"{cat.upper()} critique sur {host.hostname} ({value:.1f}%)")
    elif value >= warn:
        open_alert(db, Alert, host.id, "warning", f"{cat.upper()} élevé sur {host.hostname} ({value:.1f}%)")
    else:
        # Si la valeur est revenue à la normale, on clôt l’alerte
        resolve_alert(db, Alert, host.id, cat, cat.upper())

# ---------------------------------------------------------------
# Renvoie la sévérité ("normal", "warning", "critical")
# ---------------------------------------------------------------
def get_severity(category: str, value: float, host=None) -> str:
    """Renvoie la sévérité selon les seuils (host personnalisés si dispo)."""
    if not isinstance(value, (int, float)):
        return "normal"

    cat = category.lower()

    # Seuils par défaut
    default_thresholds = {
        "cpu": {"warning": 80, "critical": 90},
        "ram": {"warning": 85, "critical": 95},
        "storage": {"warning": 85, "critical": 95},
    }

    thresholds = default_thresholds.get(cat, {"warning": 80, "critical": 90})

    # Si l’hôte a des seuils personnalisés
    if host and getattr(host, "thresholds", None):
        custom = host.thresholds.get(cat)
        if custom and isinstance(custom, dict):
            thresholds.update({k: v for k, v in custom.items() if isinstance(v, (int, float))})

    warn = thresholds.get("warning", 80)
    crit = thresholds.get("critical", 90)

    # Détermination du niveau
    if value > crit:
        return "critical"
    elif value > warn:
        return "warning"
    else:
        return "normal"
