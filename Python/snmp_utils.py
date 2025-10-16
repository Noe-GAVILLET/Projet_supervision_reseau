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
    """
    Retourne les métriques SNMP pour une catégorie donnée.
    Catégories supportées: system, cpu, storage, interfaces
    """
    if category == "system":
        # Infos système de base
        return {
            **snmp_get(ip, community, port, "1.3.6.1.2.1.1.1.0"),  # sysDescr
            **snmp_get(ip, community, port, "1.3.6.1.2.1.1.3.0"),  # sysUpTime
            **snmp_get(ip, community, port, "1.3.6.1.2.1.1.5.0"),  # sysName
        }
    
    elif category == "ram":
        # RAM (mémoires spécifiques)
        descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3")
        size = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5")
        used = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6")

        results = {}
        for oid, name in descr.items():
            if name.lower() in [
                "physical memory", "virtual memory", "cached memory", "shared memory",
                "memory buffers", "available memory"
            ]:
                idx = oid.split(".")[-1]
                try:
                    total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0))
                    used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0))
                    results[name] = {
                        "used": used_val,
                        "total": total,
                    }
                except ValueError:
                    continue
        return results

    elif category == "cpu":
        # Charge CPU (hrProcessorLoad)
        return snmp_walk(ip, community, port, "1.3.6.1.2.1.25.3.3.1.2", limit=10)

    elif category == "storage":
        # Stockage (hrStorageDescr, hrStorageSize, hrStorageUsed)
        descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3", limit=20)
        size = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5", limit=20)
        used = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6", limit=20)

        results = {}
        for oid, name in descr.items():
            # ⛔️ Filtrer la mémoire pour éviter le doublon avec "ram"
            if "memory" in name.lower():
                continue

            idx = oid.split(".")[-1]
            try:
                total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0))
                used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0))
                results[name] = {
                    "used": used_val,
                    "total": total,
                }
            except ValueError:
                continue
        return results

    elif category == "interfaces":
        # Interfaces réseau (ifDescr, ifOperStatus)
        descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.2", limit=10)
        status = snmp_walk(ip, community, port, "1.3.6.1.2.1.2.2.1.8", limit=10)

        results = {}
        for oid, name in descr.items():
            idx = oid.split(".")[-1]
            state = status.get(f"1.3.6.1.2.1.2.2.1.8.{idx}", "unknown")
            results[name] = "up" if state == "1" else "down"
        return results

    else:
        raise ValueError(f"Catégorie SNMP inconnue : {category}")

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

