from flask import Blueprint, jsonify, request, abort
from snmp_utils import get_metrics
from db_utils import upsert_current_metric, open_alert
from models import Measurement, Alert, Host
from datetime import datetime, timedelta
from database import db
from seuils import check_thresholds

bp = Blueprint("api_poll", __name__, url_prefix="/api/poll")


# =====================================================================
# 🔹 Fonction utilitaire : enregistre les mesures d’une catégorie SNMP
# =====================================================================
def store_measurements_for_category(db, host, cat, data):
    """Gère l’insertion des mesures selon la catégorie SNMP."""

    # --- 🔸 INTERFACES ---
    if cat == "interfaces":
        for iface_name, iface_info in data.items():
            in_val = iface_info.get("in_mbps", 0.0)
            out_val = iface_info.get("out_mbps", 0.0)
            state = iface_info.get("state", "unknown")

            # Débits (en Mbps)
            db.session.add(Measurement(
                host_id=host.id,
                oid=f"{iface_name}.in",
                metric=f"{iface_name}.in",
                value=str(in_val),
                meta=cat
            ))
            db.session.add(Measurement(
                host_id=host.id,
                oid=f"{iface_name}.out",
                metric=f"{iface_name}.out",
                value=str(out_val),
                meta=cat
            ))

            # État de l’interface
            upsert_current_metric(db, host.id, f"{iface_name}.state", iface_name, state, meta=cat)

        return

    # --- 🔸 RAM / STORAGE ---
    if cat in ("ram", "storage"):
        for metric, val in data.items():
            if isinstance(val, dict) and "used" in val and "total" in val:
                pct = val.get("pct", 0)
                label = metric.split(".")[0]

                upsert_current_metric(db, host.id, label, label, pct, meta=cat)
                db.session.add(Measurement(
                    host_id=host.id,
                    oid=metric,
                    metric=label,
                    value=str(pct),
                    meta=cat
                ))
                check_thresholds(db, host, cat, metric, pct, Alert)
        return

    # --- 🔸 CPU / SYSTEM / AUTRES ---
    for metric, val in data.items():
        upsert_current_metric(db, host.id, metric, metric, val, meta=cat)
        db.session.add(Measurement(
            host_id=host.id,
            oid=metric,
            metric=metric,
            value=str(val),
            meta=cat
        ))
        check_thresholds(db, host, cat, metric, val, Alert)


# =====================================================================
# 🔹 POLL D’UN HOST UNIQUE
# =====================================================================
@bp.route("/<int:host_id>", methods=["GET"])
def poll_host_api(host_id):
    host = Host.query.get(host_id)
    if not host:
        abort(404, description="Host introuvable")

    result = {}
    errors = []

    for cat in (host.snmp_categories or []):
        try:
            # 🔹 Récupère le nom du groupe lié (linux / pfsense / windows)
            group_name = host.group.name if host.group else None

            data = get_metrics(
                host.ip,
                host.snmp_community,
                host.port,
                cat,
                host_id=host.id,
                group_name=group_name
            )

            result[cat] = data
            print(f"[DEBUG POLL] {host.hostname} [{group_name or 'default'}] → {cat} ({len(data)} métriques)")

            store_measurements_for_category(db, host, cat, data)

        except Exception as e:
            msg = f"Erreur SNMP ({cat}) sur {host.hostname}: {e}"
            print(f"[ERROR] {msg}")
            errors.append(msg)
            open_alert(db, Alert, host.id, severity="warning", message=msg)

    db.session.commit()

    return jsonify({
        "host": host.hostname,
        "ip": host.ip,
        "group": group_name,
        "categories": host.snmp_categories,
        "metrics": result,
        "errors": errors,
    })


# =====================================================================
# 🔹 POLL DE TOUS LES HOSTS
# =====================================================================
@bp.route("/all", methods=["GET"])
def poll_all_hosts():
    hosts = Host.query.all()
    summary = []

    for h in hosts:
        try:
            group_name = h.group.name if h.group else None
            cat_metrics = {}

            for cat in (h.snmp_categories or []):
                data = get_metrics(
                    h.ip,
                    h.snmp_community,
                    h.port,
                    cat,
                    host_id=h.id,
                    group_name=group_name
                )
                cat_metrics[cat] = data

                print(f"[DEBUG POLL] {h.hostname} [{group_name or 'default'}] → {cat} ({len(data)} métriques)")
                store_measurements_for_category(db, h, cat, data)

            summary.append({
                "host": h.hostname,
                "ip": h.ip,
                "group": group_name,
                "metrics": cat_metrics
            })

        except Exception as e:
            msg = f"Erreur SNMP sur {h.hostname}: {e}"
            print(f"[ERROR] {msg}")
            open_alert(db, Alert, h.id, severity="warning", message=msg)
            summary.append({
                "host": h.hostname,
                "ip": h.ip,
                "group": group_name,
                "error": str(e)
            })

    db.session.commit()
    return jsonify(summary)


# =====================================================================
# 🔹 HISTORIQUE DES MÉTRIQUES (par catégorie)
# =====================================================================
@bp.route("/metrics/<int:host_id>/<string:category>", methods=["GET"])
def metrics_history(host_id, category):
    """
    Ex: GET /api/poll/metrics/1/cpu?minutes=5
    Retourne l'historique des métriques pour un host et une catégorie SNMP.
    """
    try:
        minutes = int(request.args.get("minutes", 5))
    except ValueError:
        minutes = 5

    since = datetime.utcnow() - timedelta(minutes=minutes)

    rows = (
        db.session.query(Measurement)
        .filter(Measurement.host_id == host_id)
        .filter(Measurement.meta.like(f"%{category}%"))
        .filter(Measurement.ts >= since)
        .order_by(Measurement.ts.asc())
        .limit(1000)
        .all()
    )

    data = []
    for r in rows:
        try:
            val = float(r.value)
        except (ValueError, TypeError):
            continue

        metric_name = r.oid if category == "interfaces" else r.metric

        data.append({
            "timestamp": r.ts.isoformat(),
            "metric": metric_name,
            "value": val
        })

    return jsonify(data)
