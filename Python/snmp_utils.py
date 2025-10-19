from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, getCmd, nextCmd
)
from datetime import datetime
from models import Measurement
from database import db

# ─────────────────────────────────────────────
# 🔹 Libellés lisibles pour la catégorie "system"
# ─────────────────────────────────────────────
SYSTEM_OID_LABELS = {
    '1.3.6.1.2.1.1.1.0': 'OS Type',
    '1.3.6.1.2.1.1.3.0': 'Uptime',
    '1.3.6.1.2.1.1.5.0': 'Hostname',
}


def format_sysuptime(ticks):
    seconds = int(ticks) / 100  # uptime = centièmes de secondes
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{int(days)}d {int(hours)}h {int(minutes)}m"


# ─────────────────────────────────────────────
# 🔹 Fonctions SNMP de base
# ─────────────────────────────────────────────
def snmp_get(ip: str, community: str, port: int, oid: str):
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((ip, port), timeout=2, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid))
    )

    errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
    if errorIndication:
        raise Exception(errorIndication)
    if errorStatus:
        raise Exception(f"{errorStatus.prettyPrint()} at {errorIndex}")

    return {str(name): str(val) for name, val in varBinds}


def snmp_walk(ip: str, community: str, port: int, oid: str, limit: int = 50):
    results = {}
    count = 0
    for (errInd, errStat, errIdx, varBinds) in nextCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((ip, port), timeout=2, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False
    ):
        if errInd:
            raise Exception(errInd)
        if errStat:
            raise Exception(f"{errStat.prettyPrint()} at {errIdx}")

        for name, val in varBinds:
            results[str(name)] = str(val)

        count += 1
        if count >= limit:
            break
    return results


# ─────────────────────────────────────────────
# 🔹 Calcul du débit en Mbps entre deux sondes
# ─────────────────────────────────────────────
def calculate_rate(current_value, previous_value, previous_ts, current_ts):
    """Convertit la différence d’octets en Mbps (bits/sec / 1e6)."""
    try:
        current = int(current_value)
        previous = int(previous_value)
    except (ValueError, TypeError):
        return 0.0

    delta_t = (current_ts - previous_ts).total_seconds()
    if delta_t <= 0:
        return 0.0

    delta_bytes = current - previous
    if delta_bytes < 0:
        delta_bytes += 2**32  # gestion overflow 32-bit

    return round((delta_bytes * 8) / (delta_t * 1_000_000), 3)


# ─────────────────────────────────────────────
# 🔹 Fonction principale de récupération des métriques
# ─────────────────────────────────────────────
def get_metrics(ip: str, community: str, port: int, category: str, host_id=None):
    if category == "system":
        return {
            **snmp_get(ip, community, port, "1.3.6.1.2.1.1.1.0"),
            **snmp_get(ip, community, port, "1.3.6.1.2.1.1.3.0"),
            **snmp_get(ip, community, port, "1.3.6.1.2.1.1.5.0"),
        }

    elif category == "ram":
        descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3", limit=30)
        size = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5", limit=30)
        used = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6", limit=30)
        results = {}
        for oid, name in descr.items():
            if "physical memory" not in name.lower():
                continue
            idx = oid.split(".")[-1]
            try:
                total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0))
                used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0))
                pct = round(used_val / total * 100, 2) if total > 0 else 0
                results["Physical memory"] = {"used": used_val, "total": total, "pct": pct}
            except ValueError:
                continue
        return results

    elif category == "cpu":
        return snmp_walk(ip, community, port, "1.3.6.1.2.1.25.3.3.1.2", limit=10)

    elif category == "storage":
        descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3", limit=30)
        size = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5", limit=30)
        used = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6", limit=30)
        results = {}
        for oid, name in descr.items():
            nl = name.lower()
            if any(sub in nl for sub in ["virtual", "physical", "cached", "shared", "/run", "/dev/shm", "/tmp"]):
                continue
            idx = oid.split(".")[-1]
            try:
                total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0))
                used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0))
                pct = round(used_val / total * 100, 2) if total > 0 else 0
                results[name] = {"used": used_val, "total": total, "pct": pct}
                results[f"{name}.pct"] = pct
            except ValueError:
                continue
        return results

    elif category == "interfaces":
        ifDescr = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.2")
        ifOperStatus = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.8")
        ifInOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.31.1.1.1.6")
        ifOutOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.31.1.1.1.10")

        if not ifInOctets:
            ifInOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.10")
        if not ifOutOctets:
            ifOutOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.16")

        results = {}
        for descr_oid, name in ifDescr.items():
            idx = descr_oid.split(".")[-1]
            status_raw = str(ifOperStatus.get(f"1.3.6.1.2.1.2.2.1.8.{idx}", "2")).lower()
            raw_in = ifInOctets.get(f"1.3.6.1.2.1.31.1.1.1.6.{idx}", "0")
            raw_out = ifOutOctets.get(f"1.3.6.1.2.1.31.1.1.1.10.{idx}", "0")

            # État interface
            if "up" in status_raw or status_raw.endswith("1"):
                state = "up"
            elif "down" in status_raw or status_raw.endswith("2"):
                state = "down"
            else:
                state = "unknown"

            try:
                in_oct = int(str(raw_in).split(":")[-1].strip())
                out_oct = int(str(raw_out).split(":")[-1].strip())
            except Exception:
                in_oct, out_oct = 0, 0

            info = {"state": state, "in": in_oct, "out": out_oct}

            # 🔹 Calcul du débit à partir de la dernière mesure
            if host_id:
                prev_in = (
                    Measurement.query.filter_by(host_id=host_id, oid=f"{name}.in")
                    .order_by(Measurement.ts.desc())
                    .first()
                )
                prev_out = (
                    Measurement.query.filter_by(host_id=host_id, oid=f"{name}.out")
                    .order_by(Measurement.ts.desc())
                    .first()
                )
                now = datetime.utcnow()
                if prev_in:
                    info["in_mbps"] = calculate_rate(in_oct, prev_in.value, prev_in.ts, now)
                else:
                    info["in_mbps"] = 0.0
                if prev_out:
                    info["out_mbps"] = calculate_rate(out_oct, prev_out.value, prev_out.ts, now)
                else:
                    info["out_mbps"] = 0.0
            else:
                info["in_mbps"] = 0.0
                info["out_mbps"] = 0.0

            results[name] = info

        return results


# ─────────────────────────────────────────────
# 🔹 Autres fonctions utilitaires
# ─────────────────────────────────────────────
def get_severity(category, pct):
    if category == "ram":
        if pct > 90:
            return "critical"
        elif pct > 80:
            return "warning"
        return "normal"
    elif category == "storage":
        if pct > 95:
            return "critical"
        elif pct > 85:
            return "warning"
        return "normal"
    return "normal"
