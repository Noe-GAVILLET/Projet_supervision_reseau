# Tutoriel d'installation et de configuration SNMPv2 sur Debian 11

Ce tutoriel vous guidera pour installer et configurer **SNMPv2** (Simple Network Management Protocol) sur une machine **Debian 11**.

---

## Prérequis
Avant de commencer, assurez-vous que vous avez les **privilèges root** ou que vous pouvez exécuter des commandes `sudo`.

---

## Étape 1 : Installation des paquets nécessaires
Nous allons installer les paquets `snmpd` (le démon SNMP) et `snmp` (les outils SNMP).

```bash
sudo apt-get update
sudo apt-get install snmpd snmp
```

---

## Étape 2 : Activer et démarrer le service SNMP
Une fois l'installation terminée, activez et démarrez le service **snmpd** :

```bash
sudo systemctl enable snmpd
sudo systemctl start snmpd
```

---

## Étape 3 : Vérifier l'écoute du port SNMP
Vous pouvez vérifier si le service SNMP est bien en écoute sur le port **161** avec la commande `ss` :

```bash
ss -ulnp
```

Exemple de sortie :
```
State     Recv-Q    Send-Q       Local Address:Port        Peer Address:Port    Process                                                                         
UNCONN    0         0                127.0.0.1:161              0.0.0.0:* 
```

---

## Étape 4 : Configuration du fichier `snmpd.conf`
Éditez le fichier de configuration SNMP :

```bash
sudo nano /etc/snmp/snmpd.conf
```

Ajoutez ou modifiez les lignes suivantes pour activer **SNMPv2** avec une communauté publique (lecture seule) :

```
rocommunity public
```

Vous pouvez personnaliser la communauté pour plus de sécurité.

---

## Étape 5 : Redémarrer le service SNMP
Après avoir modifié le fichier de configuration, redémarrez le service :

```bash
sudo systemctl restart snmpd
sudo systemctl status snmpd
```

---

## Étape 6 : Vérification avec `snmpwalk`
Testez la configuration avec la commande `snmpwalk` :

```bash
snmpwalk -v1 -c public 127.0.0.1
```

Exemple de sortie :
```
iso.3.6.1.2.1.1.1.0 = STRING: "Linux debian 6.12.43+deb13-amd64 #1 SMP PREEMPT_DYNAMIC Debian 6.12.43-1 (2025-08-27) x86_64"
iso.3.6.1.2.1.1.2.0 = OID: iso.3.6.1.4.1.8072.3.2.10
iso.3.6.1.2.1.1.3.0 = Timeticks: (97087) 0:16:10.87
iso.3.6.1.2.1.1.4.0 = STRING: "Me <me@example.org>"
iso.3.6.1.2.1.1.5.0 = STRING: "debian"
iso.3.6.1.2.1.1.6.0 = STRING: "Sitting on the Dock of the Bay"
...
```

---

## Conclusion
Vous avez maintenant installé et configuré **SNMPv2** sur votre serveur **Debian 11**.  
Vous pouvez utiliser `snmpwalk` pour interroger des informations SNMP ou configurer des **outils de supervision réseau** afin de collecter ces données.
