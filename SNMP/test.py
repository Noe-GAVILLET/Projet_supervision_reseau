import time
import subprocess
import re

COMMUNITY = 'public'
HOST = '10.238.110.100'
OID_IN_OCTETS = '1.3.6.1.2.1.2.2.1.10.4'
OID_OUT_OCTETS = '1.3.6.1.2.1.2.2.1.16.4'
INTERVAL = 5

def get_octets(oid):
    """Récupère la valeur SNMP via la commande snmpget"""
    try:
        cmd = ['snmpget', '-v2c', '-c', COMMUNITY, HOST, oid]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            print(f"Erreur SNMP : {result.stderr}")
            return None
        
        # Parse la sortie pour extraire la valeur
        # Format attendu : "OID = Counter32: 12345"
        match = re.search(r':\s*(\d+)', result.stdout)
        if match:
            return int(match.group(1))
        return None
    except Exception as e:
        print(f"Erreur : {e}")
        return None

def format_debit(bps):
    """Formatte le débit en unités lisibles"""
    if bps >= 1_000_000_000:
        return f"{bps/1_000_000_000:.2f} Gbit/s"
    elif bps >= 1_000_000:
        return f"{bps/1_000_000:.2f} Mbit/s"
    elif bps >= 1_000:
        return f"{bps/1_000:.2f} Kbit/s"
    else:
        return f"{bps:.2f} bit/s"

if __name__ == "__main__":
    print(f"Surveillance SNMP de {HOST}")
    print(f"Interface index 4 - Intervalle : {INTERVAL}s\n")
    
    prev_in = get_octets(OID_IN_OCTETS)
    prev_out = get_octets(OID_OUT_OCTETS)
    
    if prev_in is None or prev_out is None:
        print("Impossible de récupérer les valeurs initiales. Vérifiez la connectivité SNMP.")
        exit(1)
    
    while True:
        time.sleep(INTERVAL)
        
        curr_in = get_octets(OID_IN_OCTETS)
        curr_out = get_octets(OID_OUT_OCTETS)
        
        if curr_in is not None and curr_out is not None:
            # Gestion du wrap-around pour compteurs 32 bits
            delta_in = curr_in - prev_in if curr_in >= prev_in else (2**32 + curr_in - prev_in)
            delta_out = curr_out - prev_out if curr_out >= prev_out else (2**32 + curr_out - prev_out)
            
            # Calcul du débit en bits par seconde
            debit_in_bps = (delta_in * 8) / INTERVAL
            debit_out_bps = (delta_out * 8) / INTERVAL
            
            print(f"IN : {format_debit(debit_in_bps):>15} | OUT : {format_debit(debit_out_bps):>15}")
            
            prev_in = curr_in
            prev_out = curr_out
