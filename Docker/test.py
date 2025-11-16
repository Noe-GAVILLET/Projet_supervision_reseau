import subprocess
import ipaddress
from tqdm import tqdm

def snmp_get(ip, community="public"):
    try:
        cmd = ["snmpget", "-v2c", "-c", community, str(ip), "1.3.6.1.2.1.1.5.0"]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=1).decode()
        return output.strip()
    except:
        return None


def scan_network(network, community="public"):
    net = ipaddress.ip_network(network)
    hosts = list(net.hosts())
    found = []

    print(f"Scan SNMP sur {network} communauté '{community}' (Ctrl+C pour arrêter)\n")

    try:
        for ip in tqdm(hosts, desc="Progression", unit="IP"):
            result = snmp_get(ip, community)
            if result:
                found.append((str(ip), result))
    except KeyboardInterrupt:
        print("\n\nScan interrompu par l'utilisateur.")
    
    print("\n=== Résultats SNMP trouvés ===")
    if not found:
        print("Aucun hôte SNMP trouvé.")
    else:
        for ip, sysname in found:
            print(f"{ip} → {sysname}")


if __name__ == "__main__":
    scan_network("192.168.1.0/24", "public")
