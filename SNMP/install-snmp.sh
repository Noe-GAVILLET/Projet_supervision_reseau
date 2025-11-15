#!/bin/bash

set -e

echo "=== Installation de SNMP et SNMPD ==="
apt update -y
apt install -y snmp snmpd

echo "=== Sauvegarde de l'ancienne configuration ==="
if [ -f /etc/snmp/snmpd.conf ]; then
    mv /etc/snmp/snmpd.conf /etc/snmp/snmpd.conf.bak_$(date +%F_%H%M%S)
fi

echo "=== Création du fichier /etc/snmp/snmpd.conf ==="

cat << 'EOF' > /etc/snmp/snmpd.conf
###############################################################################
# Fichier de configuration SNMPD pour projet de supervision
# Agent : net-snmp (snmpd)
###############################################################################

master agentx

# ---------------------------------------------------------------------------
# 1. Définition de la communauté
#    "public" = communauté SNMP v2c en lecture seule
# ---------------------------------------------------------------------------
rocommunity public

# ---------------------------------------------------------------------------
# 2. Identification de l’agent
# ---------------------------------------------------------------------------
sysLocation    Lab Debian VM
sysContact     Admin <admin@example.org>
sysName        debian-supervised

# ---------------------------------------------------------------------------
# 3. Vues SNMP (définissent ce qui est visible)
#    Ici : on inclut TOUT l’arbre MIB (.1)
# ---------------------------------------------------------------------------
view   all    included   .1    80

# ---------------------------------------------------------------------------
# 4. Contrôles d’accès
#    - notConfigGroup : groupe par défaut
#    - any / noauth   : pas d’authentification (SNMP v1/v2c)
#    - exact all none none : lecture seule
# ---------------------------------------------------------------------------
access  notConfigGroup "" any noauth exact all none none

# ---------------------------------------------------------------------------
# 5. Désactivation des restrictions "systemonly"
# ---------------------------------------------------------------------------
# (Déjà géré : l’ancienne conf a été remplacée)

# ---------------------------------------------------------------------------
# 6. MIBs standards déjà incluses par net-snmp
# ---------------------------------------------------------------------------
EOF

echo "=== Redémarrage du service SNMPD ==="
systemctl restart snmpd
systemctl enable snmpd

echo "=== Installation terminée ! ==="
echo "Tester avec : snmpwalk -v2c -c public localhost"
