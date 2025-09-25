from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, getCmd, nextCmd
)


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

    elif category == "cpu":
        # Charge CPU (hrProcessorLoad)
        return snmp_walk(ip, community, port, "1.3.6.1.2.1.25.3.3.1.2", limit=10)

    elif category == "storage":
        # Stockage (hrStorageDescr, hrStorageSize, hrStorageUsed)
        descr = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.3", limit=10)
        size = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.5", limit=10)
        used = snmp_walk(ip, community, port, "1.3.6.1.2.1.25.2.3.1.6", limit=10)

        results = {}
        for oid, val in descr.items():
            idx = oid.split(".")[-1]
            total = int(size.get(f"1.3.6.1.2.1.25.2.3.1.5.{idx}", 0))
            used_val = int(used.get(f"1.3.6.1.2.1.25.2.3.1.6.{idx}", 0))
            results[val] = f"{used_val}/{total} unités"
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
        
