import time
import subprocess
import re

COMMUNITY = 'public'
HOST = '10.238.110.100'
OID_IN_OCTETS = '1.3.6.1.2.1.2.2.1.10.4'
OID_OUT_OCTETS = '1.3.6.1.2.1.2.2.1.16.4'
INTERVAL = 10

def get_traffic():
    """Récupère IN et OUT en une seule requête"""
    try:
        cmd = ['snmpget', '-v2c', '-c', COMMUNITY, '-t', '3', HOST, OID_IN_OCTETS, OID_OUT_OCTETS]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            return None, None

        # Parse les deux valeurs
        matches = re.findall(r':\s*(\d+)', result.stdout)
        if len(matches) >= 2:
            return int(matches[0]), int(matches[1])
        return None, None
    except:
        return None, None

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
    print(f"Surveillance SNMP de {HOST} - Interface index 4\n")

    prev_in, prev_out = get_traffic()
    if prev_in is None:
        print("Impossible de récupérer les valeurs initiales.")
        exit(1)

    while True:
        time.sleep(INTERVAL)

        curr_in, curr_out = get_traffic()
        if curr_in is None:
            print(f"[{time.strftime('%H:%M:%S')}] [ERREUR] Échec SNMP")
            continue

        delta_in = curr_in - prev_in if curr_in >= prev_in else (2**32 + curr_in - prev_in)
        delta_out = curr_out - prev_out if curr_out >= prev_out else (2**32 + curr_out - prev_out)

        debit_in_bps = (delta_in * 8) / INTERVAL
        debit_out_bps = (delta_out * 8) / INTERVAL

        print(f"[{time.strftime('%H:%M:%S')}] IN : {format_debit(debit_in_bps):>15} | OUT : {format_debit(debit_out_bps):>15}")

        prev_in, prev_out = curr_in, curr_out
