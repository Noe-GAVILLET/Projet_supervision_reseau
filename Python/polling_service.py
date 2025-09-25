# polling_service.py
from typing import Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from snmp_utils import poll_host_v2c
from app import db, Host  # si tu préfères, extrais tes modèles dans models.py

def poll_all_hosts(max_workers: int = 10) -> Dict[str, Dict]:
    """Interroge tous les hôtes de la BDD en parallèle. Renvoie {hostname: data}."""
    hosts = Host.query.order_by(Host.hostname.asc()).all()
    results: Dict[str, Dict] = {}

    def _poll_one(h: Host):
        cats = h.snmp_categories or ["system"]
        return h.hostname, poll_host_v2c(h.ip, h.snmp_community or "public", h.port or 161, cats)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_poll_one, h) for h in hosts]
        for f in as_completed(futures):
            try:
                name, data = f.result()
                results[name] = data
            except Exception as e:
                # on garde l'erreur côté résultat (utile pour l'UI)
                results[name] = {"error": str(e)}
    return results
