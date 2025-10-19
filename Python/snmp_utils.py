from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, getCmd, nextCmd
)

SYSTEM_OID_LABELS = {
    '1.3.6.1.2.1.1.1.0': 'OS Type',
    '1.3.6.1.2.1.1.3.0': 'Uptime',
    '1.3.6.1.2.1.1.5.0': 'Hostname',
}

def format_sysuptime(ticks):
    seconds = int(ticks) / 100  # car uptime = centièmes de seconde
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{int(days)}d {int(hours)}h {int(minutes)}m"

def snmp_get(ip: str, community: str, port: int, oid: str):
    """SNMP GET d'un seul OID."""
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),  # v2c
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
    """SNMP WALK d'un OID, avec limite pour éviter des boucles infinies."""
    results = {}
    count = 0
    for (errInd, errStat, errIdx, varBinds) in nextCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),  # v2c
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


def get_metrics(ip: str, community: str, port: int, category: str):
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
            name_lower = name.lower()
            if "physical memory" not in name_lower:
                continue

            idx = oid.split(".")[-1]
            try:
                total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0))
                used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0))
                pct = round(used_val / total * 100, 2) if total > 0 else 0

                results["Physical memory"] = {
                    "used": used_val,
                    "total": total,
                    "pct": pct
                }

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
            name_lower = name.lower()
            if any(sub in name_lower for sub in [
                "virtual memory", "physical memory", "cached", "shared", "available",
                "/run", "/dev/shm", "/tmp", "/lock", "/credentials", "/user"
            ]):
                continue

            idx = oid.split(".")[-1]
            try:
                total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0))
                used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0))
                pct = round(used_val / total * 100, 2) if total > 0 else 0

                results[name] = {
                    "used": used_val,
                    "total": total,
                    "pct": pct
                }

                results[f"{name}.pct"] = pct  # Pour graphe
            except ValueError:
                continue
        return results

    elif category == "interfaces":
        # OIDs SNMP standard
        ifDescr = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.2")
        ifOperStatus = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.8")

        # Compteurs 64 bits (préférés si dispo)
        ifInOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.31.1.1.1.6")
        ifOutOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.31.1.1.1.10")

        # Si non supportés → fallback 32 bits
        if not ifInOctets:
            ifInOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.10")
        if not ifOutOctets:
            ifOutOctets = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.16")

        results = {}

        for descr_oid, name in ifDescr.items():
            idx = descr_oid.split(".")[-1]
            raw_status = str(ifOperStatus.get(f"1.3.6.1.2.1.2.2.1.8.{idx}", "2")).strip().lower()
            raw_in = ifInOctets.get(f"1.3.6.1.2.1.31.1.1.1.6.{idx}", None) or ifInOctets.get(f"1.3.6.1.2.1.2.2.1.10.{idx}", "0")
            raw_out = ifOutOctets.get(f"1.3.6.1.2.1.31.1.1.1.10.{idx}", None) or ifOutOctets.get(f"1.3.6.1.2.1.2.2.1.16.{idx}", "0")

            # 🧠 Détection robuste de l’état (bien dans la boucle cette fois)
            if "up" in raw_status:
                state = "up"
            elif "down" in raw_status:
                state = "down"
            elif raw_status.endswith("1") or raw_status == "1":
                state = "up"
            elif raw_status.endswith("2") or raw_status == "2":
                state = "down"
            else:
                state = "unknown"

            try:
                in_oct = int(str(raw_in).split(":")[-1].strip())
                out_oct = int(str(raw_out).split(":")[-1].strip())
            except Exception:
                in_oct, out_oct = 0, 0

            results[name] = {
                "state": state,
                "in": in_oct,
                "out": out_oct
            }

        return results


def get_storage_metrics(ip, community="public", port=161):
    """
    Retourne les infos de stockage normalisées :
    {
      "Physical memory": {"used": 1200, "total": 2048},
      "/": {"used": 15, "total": 100},
      ...
    }
    """
    storage = {}

    # Exemple OID (Host Resources MIB: hrStorage)
    # 1.3.6.1.2.1.25.2.3.1.3 = hrStorageDescr
    # 1.3.6.1.2.1.25.2.3.1.5 = hrStorageSize
    # 1.3.6.1.2.1.25.2.3.1.6 = hrStorageUsed

    descrs = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3")
    sizes = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5")
    useds = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6")

    for idx, descr in descrs.items():
        name = str(descr)
        total = int(sizes.get(idx, 0))
        used = int(useds.get(idx, 0))

        storage[name] = {
            "used": used,
            "total": total,
        }

    return storage

def get_severity(category, pct):
    if category == "ram":
        if pct > 90:
            return "critical"
        elif pct > 80:
            return "warning"
        else:
            return "normal"
    elif category == "storage":
        if pct > 95:
            return "critical"
        elif pct > 85:
            return "warning"
        else:
            return "normal"
    return "normal"