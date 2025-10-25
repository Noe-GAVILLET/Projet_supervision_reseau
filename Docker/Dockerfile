FROM python:3.11-slim

# Installer outils utiles
RUN apt update && apt install -y iputils-ping snmp netcat-openbsd && apt clean

WORKDIR /app

# Copier fichiers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose Flask port
EXPOSE 5000

# Commande unique : Flask + Scheduler (comme avant)
CMD ["python", "app.py"]
