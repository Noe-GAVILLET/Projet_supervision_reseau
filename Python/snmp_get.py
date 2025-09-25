from pysnmp.hlapi import *

IP = "192.168.141.115"
COMMUNITY = "public"
PORT = 161

# ---- CPU ----
print("=== CPU (hrProcessorLoad) ===")
for (errInd, errStat, errIdx, varBinds) in nextCmd(
    SnmpEngine(),
    CommunityData(COMMUNITY, mpModel=1),
    UdpTransportTarget((IP, PORT), timeout=2, retries=1),
    ContextData(),
    ObjectType(ObjectIdentity("1.3.6.1.2.1.25.3.3.1.2")),  # hrProcessorLoad
    lexicographicMode=False
):
    if errInd:
        print("Erreur CPU:", errInd); break
    elif errStat:
        print("Erreur CPU:", errStat.prettyPrint()); break
    else:
        for oid, val in varBinds:
            print(f"CPU {oid.prettyPrint()} = {val} %")

# ---- RAM ----
print("\n=== RAM (hrStorageRam dans hrStorageTable) ===")
storage_type_oid = "1.3.6.1.2.1.25.2.3.1.2"   # hrStorageType
storage_descr_oid = "1.3.6.1.2.1.25.2.3.1.3"  # hrStorageDescr
alloc_units_oid = "1.3.6.1.2.1.25.2.3.1.4"    # hrStorageAllocationUnits
size_oid = "1.3.6.1.2.1.25.2.3.1.5"           # hrStorageSize
used_oid = "1.3.6.1.2.1.25.2.3.1.6"           # hrStorageUsed

# on récupère type, description, taille, utilisé
for (errInd, errStat, errIdx, varBinds) in nextCmd(
    SnmpEngine(),
    CommunityData(COMMUNITY, mpModel=1),
    UdpTransportTarget((IP, PORT), timeout=2, retries=1),
    ContextData(),
    ObjectType(ObjectIdentity(storage_type_oid)),
    ObjectType(ObjectIdentity(storage_descr_oid)),
    ObjectType(ObjectIdentity(alloc_units_oid)),
    ObjectType(ObjectIdentity(size_oid)),
    ObjectType(ObjectIdentity(used_oid)),
    lexicographicMode=False
):
    if errInd:
        print("Erreur RAM:", errInd); break
    elif errStat:
        print("Erreur RAM:", errStat.prettyPrint()); break
    else:
        # Chaque varBinds contient une ligne de la table
        line = {oid.prettyPrint(): val for oid, val in varBinds}
        # Filtrer uniquement la RAM
        if "1.3.6.1.2.1.25.2.1.2" in str(line.get(storage_type_oid, "")):
            descr = line.get(storage_descr_oid)
            au = int(line.get(alloc_units_oid))
            size = int(line.get(size_oid)) * au
            used = int(line.get(used_oid)) * au
            pct = used / size * 100 if size > 0 else 0
            print(f"{descr} : {used/1024/1024:.1f} MB / {size/1024/1024:.1f} MB ({pct:.1f}%)")
