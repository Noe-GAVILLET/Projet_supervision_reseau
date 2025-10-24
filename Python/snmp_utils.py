from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, getCmd, nextCmd
)
from datetime import datetime
from typing import Optional
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
# 🔹 Fonctions SNMP génériques
# ─────────────────────────────────────────────
def snmp_get(ip: str, community: str, port: int, oid: str):
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),  # SNMP v2c
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
# 🔹 Détection automatique du type d’équipement
# ─────────────────────────────────────────────
def _detect_group(ip: str, community: str, port: int) -> str:
    try:
        sysdescr = snmp_get(ip, community, port, "1.3.6.1.2.1.1.1.0")
        val = next(iter(sysdescr.values()), "").lower()
        if "pfsense" in val or "freebsd" in val:
            return "pfsense"
        if "windows" in val or "microsoft" in val:
            return "windows"
    except Exception:
        pass
    return "linux"


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
        delta_bytes += 2**32  # overflow

    return round((delta_bytes * 8) / (delta_t * 1_000_000), 3)


# ─────────────────────────────────────────────
# 🔹 Fonction principale multi-équipement
# ─────────────────────────────────────────────
def get_metrics(ip: str, community: str, port: int, category: str,
                host_id=None, group_name: Optional[str] = None):
    """
    Récupère les métriques SNMP selon la catégorie et le type d'équipement :
    linux / pfsense / windows
    """
    group = (group_name or _detect_group(ip, community, port)).lower()

    # 1️) SYSTEM
    if category == "system":
        res = {}
        for oid in ("1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.3.0", "1.3.6.1.2.1.1.5.0"):
            try:
                res.update(snmp_get(ip, community, port, oid))
            except Exception:
                continue
        # Format lisible
        if "1.3.6.1.2.1.1.3.0" in res:
            res["Uptime"] = format_sysuptime(res["1.3.6.1.2.1.1.3.0"])
        return res

    # 2️) CPU
    elif category == "cpu":
        if group in ("linux", "pfsense"):
            return snmp_walk(ip, community, port, "1.3.6.1.2.1.25.3.3.1.2", limit=10)
        if group == "windows":
            try:
                data = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.3.3.1.2", limit=10)
                if not data:
                    data = snmp_get(ip, community, port, "1.3.6.1.4.1.2021.11.11.0")
                return data
            except Exception:
                return {}
        return {}

    # 3) RAM 
    elif category == "ram":
        results = {}

        if group == "pfsense":
            # 🔹 Utilise UCD-SNMP (plus fiable sur pfSense)
            try:
                mem_total = int(snmp_get(ip, community, port, "1.3.6.1.4.1.2021.4.5.0")["1.3.6.1.4.1.2021.4.5.0"])
                mem_avail = int(snmp_get(ip, community, port, "1.3.6.1.4.1.2021.4.6.0")["1.3.6.1.4.1.2021.4.6.0"])           
            except Exception:
                return {}

            mem_used = mem_total - mem_avail
            mem_pct = round(mem_used / mem_total * 100, 2) if mem_total > 0 else 0

            results["Memory"] = {
                "used": mem_used * 1024,   # en octets
                "total": mem_total * 1024,
                "pct": mem_pct
            }
            return results

        # 🔹 Linux / Windows : HOST-RESOURCES-MIB
        else:
            descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3")   # hrStorageDescr
            alloc = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.4")   # hrStorageAllocationUnits
            size  = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5")   # hrStorageSize
            used  = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6")   # hrStorageUsed

            for oid, name in descr.items():
                # On garde uniquement la mémoire physique
                if "physical memory" not in name.lower():
                    continue

                idx = oid.split(".")[-1]
                try:
                    block_size = int(alloc.get(f"1.3.6.1.2.1.25.2.3.1.4.{idx}", 1))
                    total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0)) * block_size
                    used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0)) * block_size
                    pct = round(used_val / total * 100, 2) if total > 0 else 0

                    results["Physical memory"] = {"used": used_val, "total": total, "pct": pct}
                except Exception:
                    continue

            return results


    # 4) STORAGE (UCD-SNMP pour pfSense)
    elif category == "storage":
        results = {}

        # --- pfSense ---
        if group == "pfsense":
            try:
                descr = snmp_walk(ip, community, port, "1.3.6.1.4.1.2021.9.1.2")
                used  = snmp_walk(ip, community, port, "1.3.6.1.4.1.2021.9.1.7")
                total = snmp_walk(ip, community, port, "1.3.6.1.4.1.2021.9.1.6")
                pct   = snmp_walk(ip, community, port, "1.3.6.1.4.1.2021.9.1.9")
            except Exception:
                return {}

            for oid, mount in descr.items():
                idx = oid.split(".")[-1]
                if mount in ("/", "/var/run"):
                    try:
                        t = int(total.get(f"1.3.6.1.4.1.2021.9.1.6.{idx}", 0))
                        u = int(used.get(f"1.3.6.1.4.1.2021.9.1.7.{idx}", 0))
                        p = int(pct.get(f"1.3.6.1.4.1.2021.9.1.9.{idx}", 0))
                        results[mount] = {"used": u * 1024, "total": t * 1024, "pct": p}
                    except Exception:
                        continue

        # --- Windows / Linux : HOST-RESOURCES-MIB ---
        else:
            descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3")
            alloc = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.4")
            size  = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5")
            used  = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6")

            for oid, name in descr.items():
                # On ignore la RAM et volumes système inutiles
                if any(skip in name.lower() for skip in ("memory", "virtual", "uma", "devfs", "/run", "/tmp")):
                    continue

                idx = oid.split(".")[-1]
                try:
                    block_size = int(alloc.get(f"1.3.6.1.2.1.25.2.3.1.4.{idx}", 1))
                    total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0)) * block_size
                    used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0)) * block_size
                    pct = round(used_val / total * 100, 2) if total > 0 else 0

                    label = name.split(" ")[0] if ":" in name else name
                    results[label] = {"used": used_val, "total": total, "pct": pct}
                except Exception:
                    continue

        # --- Normalisation finale (clé .pct pour graphe) ---
        cleaned = {}
        for name, info in results.items():
            if name.startswith("/") or ":" in name:
                cleaned[name + ".pct"] = info["pct"]
            elif "mount" in info or "descr" in info:
                label = info.get("mount") or info.get("descr")
                if label:
                    cleaned[label + ".pct"] = info["pct"]

        results.update(cleaned)
        return results


    # 5️) INTERFACES
    elif category == "interfaces":
        ifDescr = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.2")
        ifOperStatus = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.8")
        ifInOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.31.1.1.1.6")
        ifOutOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.31.1.1.1.10")

        # 🔁 fallback vers IF-MIB standard si ifXTable non dispo
        if not ifInOctets:
            ifInOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.10")
        if not ifOutOctets:
            ifOutOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.16")

        results = {}

        for descr_oid, name in ifDescr.items():
            idx = descr_oid.split(".")[-1]
            lname = name.lower()

            # 🧹 Filtrage des interfaces virtuelles / inutiles
            ignored_keywords = [
                "miniport", "virtual", "npcap", "filter", "adapter-wfp", "qos",
                "native wifi", "teredo", "6to4", "wan", "debug", "kernel",
                "isatap", "vmware", "vbox", "pppoe", "bluetooth", "loopback", "microsoft"
            ]
            if any(k in lname for k in ignored_keywords):
                continue  # On skippe ces interfaces

            state_raw = ifOperStatus.get(f"1.3.6.1.2.1.2.2.1.8.{idx}", "2")
            state = "up" if state_raw.endswith("1") else "down"

            try:
                in_val = int(ifInOctets.get(f"1.3.6.1.2.1.31.1.1.1.6.{idx}", "0"))
                out_val = int(ifOutOctets.get(f"1.3.6.1.2.1.31.1.1.1.10.{idx}", "0"))
            except ValueError:
                in_val, out_val = 0, 0

            info = {"state": state, "in": in_val, "out": out_val}

            # 🕒 Calcul des débits (si host_id présent)
            if host_id:
                now = datetime.utcnow()
                prev_in = Measurement.query.filter_by(host_id=host_id, oid=f"{name}.in").order_by(Measurement.ts.desc()).first()
                prev_out = Measurement.query.filter_by(host_id=host_id, oid=f"{name}.out").order_by(Measurement.ts.desc()).first()
                info["in_mbps"] = calculate_rate(in_val, prev_in.value, prev_in.ts, now) if prev_in else 0.0
                info["out_mbps"] = calculate_rate(out_val, prev_out.value, prev_out.ts, now) if prev_out else 0.0
            else:
                info["in_mbps"], info["out_mbps"] = 0.0, 0.0

            results[name] = info

        return results


    # fallback
    return {}


# ─────────────────────────────────────────────
# 🔹 Helper pour gravité RAM/STORAGE
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
