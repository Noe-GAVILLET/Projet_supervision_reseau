from flask import Blueprint, jsonify, request, abort
from snmp_utils import get_metrics
from db_utils import upsert_current_metric, open_alert
from models import Measurement, Alert, Host
from datetime import datetime, timedelta
from database import db
from seuils import check_thresholds

bp = Blueprint("api_poll", __name__, url_prefix="/api/poll")


@bp.route("/<int:host_id>", methods=["GET"])
def poll_host_api(host_id):
    """
    Lance un poll SNMP sur un hôte spécifique et stocke les métriques
    dans current_metrics + measurements.
    """
    host = Host.query.get(host_id)
    if not host:
        abort(404, description="Host introuvable")

    result = {}
    errors = []

    for cat in (host.snmp_categories or []):
        try:
            data = get_metrics(host.ip, host.snmp_community, host.port, cat)
            print(f"[DEBUG POLL] Catégorie SNMP : {cat} → {len(data)} métriques")
            result[cat] = data

            for metric, val in data.items():
                # 🔹 RAM / STORAGE : dictionnaire {used, total, pct}
                if isinstance(val, dict) and "used" in val and "total" in val:
                    pct = val.get("pct", 0)
                    label = metric.split(".")[0]  # Ex: "Physical memory"

                    upsert_current_metric(db, host.id, label, label, pct, meta=cat)

                    db.session.add(Measurement(
                        host_id=host.id,
                        oid=metric,
                        metric=label,
                        value=str(pct),
                        meta=cat
                    ))

                    # ✅ Vérifie les seuils pour cette métrique
                    check_thresholds(db, host, cat, metric, pct, Alert)

                # 🔹 Autres : CPU, interfaces, etc.
                else:
                    upsert_current_metric(db, host.id, metric, metric, val, meta=cat)

                    db.session.add(Measurement(
                        host_id=host.id,
                        oid=metric,
                        metric=metric,
                        value=str(val),
                        meta=cat
                    ))

                    # ✅ Vérifie les seuils pour CPU et autres
                    check_thresholds(db, host, cat, metric, val, Alert)

        except Exception as e:
            msg = f"Erreur SNMP ({cat}): {e}"
            errors.append(msg)
            open_alert(db, Alert, host.id, severity="warning", message=msg)

    db.session.commit()
    return jsonify({
        "host": host.hostname,
        "ip": host.ip,
        "categories": host.snmp_categories,
        "metrics": result,
        "errors": errors,
    })


@bp.route("/all", methods=["GET"])
def poll_all_hosts():
    """
    Lance un poll SNMP sur tous les hôtes connus.
    """
    hosts = Host.query.all()
    summary = []

    for h in hosts:
        try:
            cat_metrics = {}
            for cat in (h.snmp_categories or []):
                data = get_metrics(h.ip, h.snmp_community, h.port, cat)
                cat_metrics[cat] = data
                print(f"[DEBUG POLL] {h.hostname} → catégorie {cat} ({len(data)} métriques)")

                for metric, val in data.items():
                    if isinstance(val, dict) and "used" in val and "total" in val:
                        pct = val.get("pct", 0)
                        label = metric.split(".")[0]

                        upsert_current_metric(db, h.id, label, label, pct, meta=cat)
                        db.session.add(Measurement(
                            host_id=h.id,
                            oid=metric,
                            metric=label,
                            value=str(pct),
                            meta=cat
                        ))

                        check_thresholds(db, h, cat, metric, pct, Alert)

                    else:
                        upsert_current_metric(db, h.id, metric, metric, val, meta=cat)
                        db.session.add(Measurement(
                            host_id=h.id,
                            oid=metric,
                            metric=metric,
                            value=str(val),
                            meta=cat
                        ))

                        check_thresholds(db, h, cat, metric, val, Alert)

            summary.append({
                "host": h.hostname,
                "ip": h.ip,
                "metrics": cat_metrics
            })

        except Exception as e:
            msg = f"Erreur SNMP ({h.hostname}): {e}"
            open_alert(db, Alert, h.id, severity="warning", message=msg)
            summary.append({
                "host": h.hostname,
                "ip": h.ip,
                "error": str(e)
            })

    db.session.commit()
    return jsonify(summary)


# 🔥 Historique des métriques
@bp.route("/metrics/<int:host_id>/<string:category>", methods=["GET"])
def metrics_history(host_id, category):
    """
    Ex: GET /api/poll/metrics/1/cpu?minutes=5
    Retourne l'historique des métriques pour un host donné et une catégorie SNMP.
    """
    try:
        minutes = int(request.args.get("minutes", 5))
    except ValueError:
        minutes = 5

    since = datetime.utcnow() - timedelta(minutes=minutes)

    rows = (
        db.session.query(Measurement)
        .filter(Measurement.host_id == host_id)
        .filter(Measurement.meta == category)
        .filter(Measurement.ts >= since)
        .order_by(Measurement.ts.asc())
        .limit(500)
        .all()
    )

    data = []
    for r in rows:
        try:
            val = float(r.value)
        except (ValueError, TypeError):
            continue

        data.append({
            "timestamp": r.ts.isoformat(),
            "metric": r.metric,
            "value": val
        })

    return jsonify(data)
