from flask import Blueprint, render_template, request, send_file
from models import db, Host, Group, Measurement
from datetime import datetime, timedelta
from io import BytesIO
import pandas as pd



bp = Blueprint("logs", __name__)

# ---------------------------------------------------------------------
# 🧾 Page d'affichage des logs SNMP
# ---------------------------------------------------------------------
@bp.route("/logs")
def logs_view():
    hosts = Host.query.all()
    groups = Group.query.all()

    # 🔹 Filtres URL
    host_id = request.args.get("host_id", type=int)
    group_id = request.args.get("group_id", type=int)
    category = request.args.get("category", type=str)
    duration = request.args.get("duration", "1h")

    # 🔹 Plage temporelle
    now = datetime.utcnow()
    delta_map = {
        "10m": timedelta(minutes=10),
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    start_time = now - delta_map.get(duration, timedelta(hours=1))

    # 🔹 Construction de la requête
    query = Measurement.query.join(Host).filter(Measurement.ts >= start_time)
    if host_id:
        query = query.filter(Measurement.host_id == host_id)
    if group_id:
        query = query.filter(Host.group_id == group_id)
    if category:
        # ⚠️ Le champ "meta" contient la catégorie ("cpu", "storage", etc.)
        query = query.filter(Measurement.meta.like(f'"{category}"'))

    logs = query.order_by(Measurement.ts.desc()).limit(1000).all()

    # 🔹 Mise en forme pour l'affichage
    formatted_logs = []
    for m in logs:
        host = Host.query.get(m.host_id)
        formatted_logs.append({
            "ts": m.ts.strftime("%Y-%m-%d %H:%M:%S"),
            "host": host.hostname if host else "?",
            "ip": host.ip if host else "?",
            "meta": m.meta.strip('"') if m.meta else "?",
            "metric": m.metric or m.oid,
            "value": m.value
        })

    filters = {
        "host_id": host_id,
        "group_id": group_id,
        "category": category,
        "duration": duration,
    }

    return render_template(
        "logs.html",
        logs=formatted_logs,
        hosts=hosts,
        groups=groups,
        filters=filters,
    )


# ---------------------------------------------------------------------
# 📤 Export des logs en Excel (avec filtres)
# ---------------------------------------------------------------------
@bp.route("/logs/export")
def logs_export():
    host_id = request.args.get("host_id", type=int)
    group_id = request.args.get("group_id", type=int)
    category = request.args.get("category", type=str)
    duration = request.args.get("duration", "1h")

    now = datetime.utcnow()
    delta_map = {
        "10m": timedelta(minutes=10),
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    start_time = now - delta_map.get(duration, timedelta(hours=1))

    # 🔹 Requête filtrée
    query = Measurement.query.join(Host).filter(Measurement.ts >= start_time)
    if host_id:
        query = query.filter(Measurement.host_id == host_id)
    if group_id:
        query = query.filter(Host.group_id == group_id)
    if category:
        query = query.filter(Measurement.meta.like(f'"{category}"'))

    data = query.order_by(Measurement.ts.desc()).limit(5000).all()

    # 🔹 Construction du DataFrame
    rows = []
    for m in data:
        host = Host.query.get(m.host_id)
        rows.append({
            "Horodatage": m.ts.strftime("%Y-%m-%d %H:%M:%S"),
            "Hôte": host.hostname if host else "?",
            "IP": host.ip if host else "?",
            "Catégorie": m.meta.strip('"') if m.meta else "?",
            "Métrique": m.metric or m.oid,
            "Valeur": m.value,
        })

    if not rows:
        rows.append({"Horodatage": "-", "Hôte": "-", "IP": "-", "Catégorie": "-", "Métrique": "-", "Valeur": "-"})

    df = pd.DataFrame(rows)

    # 🔹 Export Excel
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    filename = f"snmp_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
