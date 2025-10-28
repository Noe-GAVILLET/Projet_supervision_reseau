## Objectif

Permettre à un serveur de supervision (comme ton application Flask SNMP) d’interroger un hôte Windows via SNMP v2c, avec la communauté `public`, depuis n’importe quel réseau.

---

## 1. Installation du service SNMP

1. Ouvre **Server Manager**.
2. Clique sur **Add Roles and Features**.
3. Suis les étapes jusqu’à la section **Features**.
4. Coche :

   * **SNMP Service**
   * (optionnel) **SNMP WMI Provider**
5. Termine l’assistant puis redémarre le serveur si nécessaire.


## 2. Configuration du service SNMP

### Étape 1 : Ouvrir la console de configuration

1. Appuie sur `Win + R`, tape :

   ```
   services.msc
   ```
2. Trouve **Service SNMP**.
3. Clic droit → **Propriétés**.

---

### Étape 2 : Onglet **Agent**

1. Coche au minimum :

   * **Système**
   * **Physique**
   * **Internet**
2. Remplis les champs d’informations (optionnel) :

   * **Nom du contact**
   * **Localisation**

## 🔥 3. Configuration du pare-feu Windows

Ouvre PowerShell **en administrateur** et exécute :

```powershell
# Autoriser le trafic SNMP entrant
netsh advfirewall firewall add rule name="SNMP" dir=in action=allow protocol=UDP localport=161

## Résumé 

| Étape | Action                            | Commande/Interface                                             |
| ----- | --------------------------------- | -------------------------------------------------------------- |
| 1     | Installer le service SNMP         | `Add-WindowsCapability -Online -Name "SNMP.Client~~~~0.0.1.0"` |
| 2     | Configurer la communauté `public` | services.msc / registre                                        |
| 3     | Autoriser tous les réseaux        | Coche “Accepter de n’importe quel hôte”                        |
| 4     | Ouvrir le port UDP 161            | `netsh advfirewall firewall add rule ...`                      |
| 5     | Redémarrer le service SNMP        | `Restart-Service SNMP`                                         |
| 6     | Tester                            | `snmpwalk -v2c -c public <IP> 1.3.6.1.2.1.1`                   |


