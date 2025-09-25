# api_poll.py
from flask import Blueprint, jsonify, abort
from snmp_utils import poll_host_v2c
from app import db, Host
from polling_service import poll_all_hosts

bp = Blueprint("api_poll", __name__, url_prefix="/api")

@bp.get("/hosts/<int:host_id>/poll")
def api_poll_host(host_id: int):
    host = db.session.get(Host, host_id)
    if not host:
        abort(404)
    cats = host.snmp_categories or ["system"]
    data = poll_host_v2c(
        ip=host.ip,
        community=host.snmp_community or "public",
        port=host.port or 161,
        categories=cats
    )
    return jsonify({
        "host": host.hostname,
        "ip": host.ip,
        "categories": cats,
        "data": data
    })

@bp.get("/poll/all")
def api_poll_all():
    data = poll_all_hosts(max_workers=10)
    return jsonify(data)
