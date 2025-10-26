from app import app, inject_alert_info
with app.app_context():
    print(inject_alert_info())