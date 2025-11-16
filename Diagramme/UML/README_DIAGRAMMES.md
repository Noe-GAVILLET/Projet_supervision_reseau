# 📊 Diagrammes UML - Système de Supervision Réseau SNMP

## 📋 Table des Matières

1. [Vue Client Simplifié (Recommandé pour présentation)](#1-vue-client-simplifié)
2. [Séquence Complète (Détail technique)](#2-séquence-complète)
3. [Architecture Système (Infrastructure)](#3-architecture-système)
4. [Cycle de Polling SNMP (Détail algorithme)](#4-cycle-de-polling-snmp)
5. [Gestion des Alertes (Workflow notifications)](#5-gestion-des-alertes)

---

## 1️⃣ Vue Client Simplifié
**Fichier:** `sequence_diagram_client_overview.puml`

### 📌 Objectif
Présentation au client des flux métier principaux sans détails techniques.

### 🎯 Contenu
- **Phase 1**: Authentification et accès au dashboard
- **Phase 2**: Polling automatique continu (15 sec)
- **Phase 3**: Consultation des statuts équipements
- **Phase 4**: Affichage des alertes
- **Phase 5**: Gestion des alertes (acquittement)
- **Phase 6**: Configuration équipements (ajout/modification)
- **Phase 7**: Paramétrage des seuils personnalisés
- **Phase 8**: Gestion multi-utilisateurs
- **Phase 9**: Réception notifications email

### 💡 Utilisation
**✅ Idéal pour:**
- Soutenance client
- Présentation direction
- Documentation commerciale
- Démonstration fonctionnalités métier

### 🔑 Points clés mis en avant
- Supervision **automatique** et **temps réel**
- Interface web **intuitive**
- Gestion **multi-utilisateurs**
- Alertes par **email** instantanées
- **Scalabilité** système

---

## 2️⃣ Séquence Complète
**Fichier:** `sequence_diagram_supervision.puml`

### 📌 Objectif
Vue technique complète avec tous les appels système, composants et interactions.

### 🎯 Contenu

#### **Section 1: Authentification**
- Vérification identifiants en base de données
- Support dual hash (Werkzeug + SHA256 legacy)
- Gestion session Flask

#### **Section 2: Dashboard Temps Réel**
- Récupération données depuis database
- Rendu HTML avec templates Jinja2
- Affichage statuts et graphiques

#### **Section 3: Scheduler SNMP**
- Démarrage thread asynchrone daemon
- Boucle infinie 15 secondes
- Synchronisation avec app context Flask

#### **Section 4: Cycle Polling (Le cœur)**
- **4.1** Récupération tous les hosts
- **4.2** Vérification accessibilité réseau (ping)
- **4.3** Collecte SNMP (categories: system, cpu, ram, storage)
- **4.4** Parsing & formatage données
- **4.5** Stockage mesures + historique
- **4.6** Vérification seuils
- **4.7** Détection changement état (UP/DOWN)
- **4.8** Gestion transitions + alertes

#### **Section 5: Affichage Dashboard**
- GET requête utilisateur
- Récupération données fresh
- Rendu interface mise à jour

#### **Section 6: Gestion Hôtes**
- Formulaire édition
- Update base de données
- Confirmation utilisateur

#### **Section 7: Gestion Alertes**
- Liste alertes actives
- Acquittement utilisateur
- Historique complet

#### **Section 8: Gestion Utilisateurs**
- Panel administrateur
- Création comptes (admin/operator)
- Configuration abonnement alertes

### 💡 Utilisation
**✅ Idéal pour:**
- Réunion technique avec équipe dev
- Validation architecture
- Documentation technique détaillée
- Onboarding nouvelles ressources

### 🔑 Caractéristiques
- ✅ Détail **ligne par ligne**
- ✅ Tous les **services** représentés
- ✅ Gestion **d'erreurs** illustrée
- ✅ **Transactions** DB montrées
- ✅ Notifications **email** intégrées

---

## 3️⃣ Architecture Système
**Fichier:** `architecture_system.puml`

### 📌 Objectif
Vue d'ensemble de l'infrastructure et des composants système.

### 🎯 Contenu

#### **Couche Présentation (Frontend)**
```
Flask Web Server (Port 5000)
├── Templates Jinja2
│   ├── login.html → Authentification
│   ├── admin.html → Dashboard principal
│   ├── host_edit.html → Config équipement
│   ├── alerts.html → Alertes
│   └── user_list.html → Gestion users
├── Static Assets
│   ├── CSS/Bootstrap → Styling
│   ├── Chart.js → Graphiques temps réel
│   └── Plotly → Graphiques avancés
```

#### **Couche Applicative (Métier)**
```
app.py (Routes principales)
├── /login → Authentification
├── /admin → Dashboard
├── /host/* → Gestion équipements
├── /alerts → Alertes
└── /users → Gestion utilisateurs

snmp_utils.py (Collecte SNMP)
├── snmp_get() → GET unique OID
├── snmp_walk() → WALK arborescence
└── get_metrics() → Extraction catégories

poller.py (Scheduling SNMP)
├── start_scheduler() → Lancer thread
├── poll_host_metrics() → Cycle polling
└── HOST_STATUS_CACHE → Cache état

seuils.py (Détection Alertes)
├── check_thresholds() → Vérif seuils
├── get_severity() → Calcul sévérité
├── check_host_reachability() → Ping
└── detect_interface_changes() → Détect état interfaces

db_utils.py (Notification)
├── send_alert_email() → SMTP Gmail
├── open_alert() → Créer alerte
└── resolve_alert() → Fermer alerte

models.py (ORM SQLAlchemy)
├── User → Authentification
├── Host → Inventaire
├── Alert → Événements
├── CurrentMetric → État courant
├── Measurement → Historique
└── Group/Template/Tag → Metadata
```

#### **Couche Données (Backend)**
```
MySQL Database (Port 3306)
├── users
│   ├── username, email, password_hash
│   ├── role (admin/operator)
│   └── receive_alerts
├── hosts
│   ├── hostname, ip, port
│   ├── status (up/down/unknown)
│   ├── snmp_community, snmp_categories
│   ├── thresholds (JSON)
│   └── group_id, template_id
├── current_metrics
│   ├── host_id, oid (PK)
│   ├── metric, value, meta
│   └── timestamp
├── measurements (timeseries)
│   ├── id, host_id, oid
│   ├── metric, value, meta
│   └── timestamp (indexed)
├── alerts (audit trail)
│   ├── host_id, severity
│   ├── message, created_at
│   ├── acknowledged_by/at
│   └── resolved_at
└── groups, templates, tags
```

#### **Infrastructure Réseau**
```
SNMP v2c (Port 161 UDP)
├── Serveurs (Windows/Linux SNMP Agent)
├── Routeurs (Cisco/Juniper)
├── Switches (VLANs/Spanning Tree)
├── Postes clients
├── Firewalls (PFSense)
└── Autres équipements SNMP
```

#### **Système Notification**
```
Gmail SMTP (smtp.gmail.com:587)
└── TLS Encryption
    ├── send_alert_email()
    └── Boîtes email destinataires
```

#### **Logs & Monitoring**
```
logs/supervision.log (5MB rotating)
└── RotatingFileHandler
    ├── Niveaux: DEBUG → CRITICAL
    ├── 3 archives conservées
    └── Format: [timestamp] [LEVEL] [module] message
```

#### **Déploiement Docker**
```
🐳 Container python:3.11
├── Flask App
├── APScheduler (Scheduler)
├── PySQL (MySQL client)
└── Network: bridge → MySQL Container

🐳 Container MySQL:8.0
├── Port 3306
├── Volume: /data
└── Charset: UTF-8 MB4
```

### 💡 Utilisation
**✅ Idéal pour:**
- Architecture review
- Documentation infrastructure
- Planning déploiement
- Audit technique
- Justification choix technologiques

### 🔑 Technologies
- **Backend:** Python 3.11, Flask, SQLAlchemy
- **Database:** MySQL 8.0, Redis (optionnel)
- **SNMP:** pysnmp library
- **Notification:** Gmail SMTP TLS
- **Déploiement:** Docker, docker-compose
- **Frontend:** HTML5, Bootstrap, Chart.js, Plotly

---

## 4️⃣ Cycle de Polling SNMP
**Fichier:** `polling_cycle_detailed.puml`

### 📌 Objectif
Détail complet du cycle de polling qui s'exécute **toutes les 15 secondes**.

### 🎯 Contenu

#### **Initialisation (T0)**
- Démarrage scheduler en thread daemon
- Flag `_scheduler_started` pour éviter doublons
- Boucle infinie: `while True: poll_host_metrics(); sleep(15)`

#### **Itération 1 (T1-T15sec)**

##### **Étape 1: Vérification Ping**
```python
FOR EACH host IN Host.query.all():
  ping_ok = check_host_reachability(host)
  # subprocess.run(['ping', '-n', '1', host.ip])
  # return returncode == 0
```
- Teste accessibilité réseau de base
- Timeout: 2 secondes
- Compatible Windows et Linux

##### **Étape 2: Collecte SNMP (si ping OK)**
```python
IF ping_ok:
  FOR EACH category IN host.snmp_categories:
    # categories = ['system', 'cpu', 'ram', 'storage', 'interfaces']
    data = get_metrics(
      ip=host.ip,
      community=host.snmp_community,
      port=161,
      category=category
    )
    # data = dict { OID: value }
```

**Détail get_metrics():**
- `snmp_walk()` pour chaque OID racine
- Timeout: 2 sec per OID
- Retries: 1
- Parsing résultats (int, float, str conversions)
- Calculs (débit, uptime, %)

##### **Étape 3: Stockage Métriques**
```python
FOR EACH (oid, value) IN data:
  # 1️⃣ Upsert current_metrics (dernière valeur)
  upsert_current_metric(
    host_id, oid, metric, value, meta=category
  )
  # UPDATE si existe, INSERT sinon
  
  # 2️⃣ INSERT measurements (historique timeseries)
  db.session.add(Measurement(
    host_id=host_id,
    oid=oid,
    metric=metric,
    value=str(value),
    meta=category,
    ts=datetime.utcnow()
  ))
```

- **current_metrics:** 1 row par (host_id, oid)
- **measurements:** Tous les points historiques

##### **Étape 4: Vérification Seuils**
```python
FOR EACH (oid, value) IN data:
  FOR EACH category IN ['cpu', 'ram', 'storage']:
    check_thresholds(
      db=db,
      host=host,
      category=category,
      oid=oid,
      value=value,
      Alert=Alert
    )
```

**Logique seuils:**
```
default_thresholds = {
  'cpu': {'warning': 80, 'critical': 90},
  'ram': {'warning': 85, 'critical': 95},
  'storage': {'warning': 85, 'critical': 95}
}

# Override si host.thresholds personnalisé
thresholds = host.thresholds.get(category, default)

IF value >= critical:
  open_alert(host_id, 'critical', message)
  send_alert_email()
ELIF value >= warning:
  open_alert(host_id, 'warning', message)
ELSE:
  resolve_alert(host_id, category)
```

- **Cooldown:** 10 min entre emails identiques
- **Escalade:** Warning → Critical
- **Résolution:** Retour à la normale → fermeture + email confirmation

##### **Étape 5: Détection Changement État**
```python
new_status = 'down' if (not ping_ok or not snmp_ok) else 'up'
previous_status = HOST_STATUS_CACHE.get(host_id, 'unknown')

IF new_status != previous_status:
  HOST_STATUS_CACHE[host_id] = new_status
  host.status = new_status
  host.last_status_change = datetime.utcnow()
  db.session.commit()
  
  IF new_status == 'down':
    # ❌ Transition UP → DOWN
    open_alert(host_id, 'critical', 'SNMP injoignable')
  
  ELIF new_status == 'up':
    # ✅ Transition DOWN → UP
    resolve_alert(host_id, 'SNMP injoignable')
    IF previous_status == 'unknown':
      # Première détection: pas de mail
      open_alert(host_id, 'info', 'Première détection OK')
    ELSE:
      # Vraie reprise: confirmation mail
      open_alert(host_id, 'info', 'SNMP rétabli ✅')
```

- **Transition UNKNOWN → UP:** Pas d'email (première fois)
- **Transition DOWN → UP:** Email confirmation
- **Transition UP → DOWN:** Alerte critique immédiate

##### **Étape 6: Commit DB**
```python
db.session.commit()
# ✅ Toutes les changes MySQL validées
```

#### **Résumé & Boucle Continue (T15-T30sec)**
```python
📊 Résumé scan:
- 2 hosts UP
- 1 host DOWN
- 3 alertes déclenchées
- 45 métriques stockées

sleep(15)  # Attendre prochaine itération
# T30: Nouvelle itération...
```

### 🛡️ Gestion Erreurs & Résilience

#### **Exception SNMP (timeout, parse error)**
```python
try:
  data = get_metrics(...)
except Exception as e:
  log_warning(f"SNMP error for {hostname}: {e}")
  snmp_ok = False
  open_alert(host_id, 'warning', f'SNMP error: {e}')
  continue  # Next host
```

#### **Exception Base de Données**
```python
try:
  db.session.add(...)
  db.session.commit()
except Exception as e:
  db.session.rollback()
  log_error(f"Database error: {e}")
  continue  # Next host
```

#### **Exception Parsing Métrique**
```python
for oid, value in data.items():
  try:
    check_thresholds(...)
  except Exception as e:
    log_warning(f"Metric error {oid}: {e}")
    continue  # Next metric
```

### ⚡ Performance & Optimisation

#### **Index Database**
```sql
CREATE INDEX idx_alerts_created ON alerts(created_at);
CREATE INDEX idx_measurements_ts ON measurements(ts);
CREATE INDEX pk_current_metrics ON current_metrics(host_id, oid);
```
- Requêtes filtering/sorting ultra-rapides

#### **Cache Statuts En Mémoire**
```python
HOST_STATUS_CACHE = {
  1: 'up',
  2: 'down',
  3: 'unknown'
}
```
- Évite re-query si pas de changement
- Détection transition très rapide

#### **Scalabilité**
- ✅ 10+ hosts → ~60 sec scan
- ✅ 100+ hosts → ~600 sec scan
- ✅ MySQL → 10,000+ hosts possible
- ✅ Asynchrone (web non-bloquant)

### 💡 Utilisation
**✅ Idéal pour:**
- Debugging algorithme polling
- Optimisation performance
- Audit piste complète
- Formation ingénieurs
- Documentation détaillée

---

## 5️⃣ Gestion des Alertes
**Fichier:** `alert_workflow_detailed.puml`

### 📌 Objectif
Workflow complet des alertes: création, notification, acquittement, résolution.

### 🎯 Contenu

#### **Scénario 1: Seuil Dépassé - Première Alerte**
```
📡 CPU mesurée = 92%
↓
🚨 check_thresholds(): 92% >= 90% (critical)
↓
💾 open_alert(host_id=5, severity='critical', message='CPU critique 92%')
↓
🗄️ INSERT INTO alerts (id=1001, ...)
↓
📧 send_alert_email() → admin@company.fr, ops@company.fr
↓
✉️ Email reçu en inbox
↓
📌 Alerte affichée dans dashboard web
```

**Email structure:**
```
Subject: ⚠️ CRITIQUE: Srv-Web CPU
Body:
  Host: Srv-Web (192.168.1.10)
  Métrique: CPU = 92%
  Seuil: 90%
  Heure: 2025-11-16 14:30:45
  Action recommandée: Vérifier charge serveur
```

#### **Scénario 2: Cooldown - Pas de Re-email**
```
⏱️ T+10sec: Deuxième mesure CPU = 95%
↓
🚨 check_thresholds(): 95% >= 90% (critical)
↓
💾 Query Alert WHERE host_id=5 AND message LIKE '%CPU%' AND resolved_at IS NULL
↓
✅ Alerte 1001 trouvée!
  Created: 14:30:45
  Now: 14:30:55
  Duration: 10 sec < 10 min cooldown
↓
⚠️ Alerte en cooldown
  → NE PAS envoyer email (spam prevention)
  → Log seulement en base
  → Reste affichée dans dashboard
```

**Bénéfice:** Évite bombardement d'emails pour même problème

#### **Scénario 3: Retour à la Normale - Fermeture**
```
⏱️ T+15min: Troisième mesure CPU = 65%
↓
🚨 check_thresholds(): 65% < 80% (warning) → NORMAL
↓
💾 resolve_alert(host_id=5, category='CPU')
↓
🗄️ UPDATE alerts SET resolved_at=NOW() WHERE id=1001
🗄️ INSERT alerts (id=1002, severity='info', message='CPU normal 65%')
↓
📧 send_alert_email() → Confirmation reprise
↓
✉️ Email: "✅ INFO: Srv-Web - CPU Normal"
↓
📌 Dashboard affiche "Résolu" sur l'alerte
```

#### **Scénario 4: Détection Perte SNMP**
```
📡 Équipement injoignable (ping timeout)
↓
🚨 ping_ok = False
↓
💾 open_alert(host_id=7, severity='critical', 
   message='SNMP injoignable sur Router-Core')
↓
🗄️ INSERT INTO alerts
↓
📧 send_alert_email() 
  Subject: "🚨 CRITIQUE: Router-Core SNMP Down"
  Body: "IP: 192.168.100.1
         Heure: 2025-11-16 15:02:00
         → Vérifier connectivité réseau"
↓
✉️ Email envoyé immédiatement (sévérité CRITICAL)
```

#### **Scénario 5: Acquittement Utilisateur**
```
👤 Utilisateur reçoit email + consulte dashboard
↓
👆 Clique bouton "Acknowledge" sur alerte
↓
📝 POST /alert/1001/acknowledge (user_id, timestamp)
↓
🗄️ UPDATE alerts 
   SET acknowledged_by=user_id,
       acknowledged_at=NOW()
   WHERE id=1001
↓
✅ Alert marquée comme "vue"
   Display: "Acquitted by: admin@company.fr at: 14:35:30"
↓
📌 Alerte toujours active, mais signalée comme traitée
   (utile pour suivi des tâches)
```

#### **Scénario 6: Dashboard Alertes**
```
👤 GET /alerts (page liste alertes)
↓
🗄️ Query Alert WHERE resolved_at IS NULL
   ORDER BY created_at DESC
↓
📊 Display:
  ┌─────────────────────────────────────┐
  │ 🚨 CRITICAL (1001)                  │
  │ Host: Srv-Web                       │
  │ Message: CPU critique 92%           │
  │ Created: 14:30:45                   │
  │ Status: Acknowledged (admin)        │
  │ [Acknowledge] [Delete]              │
  ├─────────────────────────────────────┤
  │ ⚠️ WARNING (1003)                   │
  │ Host: Switch-Lab                    │
  │ Message: Interface eth0 DOWN        │
  │ Created: 14:45:12                   │
  │ Status: Open                        │
  │ [Acknowledge] [Delete]              │
  └─────────────────────────────────────┘
```

#### **Scénario 7: Configuration Destinataires**
```
👤 Admin → GET /users (page gestion utilisateurs)
↓
🗄️ Query users WHERE is_active=1
   Résultat:
   - admin@company.fr (receive_alerts=1) ✓
   - ops1@company.fr (receive_alerts=1) ✓
   - ops2@company.fr (receive_alerts=0) ✗
↓
👆 Admin décoche "receive_alerts" pour ops1
↓
🗄️ UPDATE users SET receive_alerts=0 WHERE id=?
↓
✅ Prochaines alertes enverront SEULEMENT à:
   - admin@company.fr
   - ops2@company.fr (si activé)
```

### 📊 État Alerte

#### **Attributs**
```
id              → Identifiant unique
host_id         → Équipement affecté
severity        → "info", "warning", "critical"
message         → Description problème
created_at      → Quand déclenché
acknowledged_by → ID utilisateur (NULL=non acquitté)
acknowledged_at → Quand acquitté
resolved_at     → Quand fermé (NULL=actif)
```

#### **Cycle de Vie**
```
1️⃣ CRÉÉE (create_at=NOW(), others=NULL)
   → Alerte fraîche, email envoyé
   
2️⃣ ACTIVE (acknowledged_by=NULL, resolved_at=NULL)
   → Visible dans dashboard
   → Attente action utilisateur
   
3️⃣ ACQUITTÉE (acknowledged_by=user_id, acknowledged_at=NOW())
   → Marquée comme "vue"
   → Restera active jusqu'à résolution
   
4️⃣ RÉSOLUE (resolved_at=NOW())
   → Problème disparu
   → Email confirmation si applicable
   → Archivée (n'apparaît plus dans liste active)
   
5️⃣ FERMÉE (suppression possible)
   → Après audit/archivage
```

### 🚨 Matrice Sévérité

| Condition | Sévérité | Email | Cooldown | Exemple |
|-----------|----------|-------|----------|---------|
| Ping ko | CRITICAL | Immédiat | 10 min | Host DOWN |
| SNMP ko | CRITICAL | Immédiat | 10 min | SNMP timeout |
| Value >= critical | CRITICAL | Immédiat | 10 min | CPU 95% (seuil 90%) |
| Value >= warning | WARNING | Non | 10 min | CPU 85% (seuil 80%) |
| Retour normal | INFO | Si was critical | - | CPU 65% (resolved) |
| État interface changé | WARNING | Non | - | Interface down |

### 💡 Utilisation
**✅ Idéal pour:**
- Training utilisateurs
- Documentation workflow alertes
- Compréhension escalade criticité
- Audit trail complet
- Debugging problèmes notification

---

## 🎯 Résumé pour Présentation Client

### 🟢 Points Forts à Mettre en Avant
1. ✅ **Supervision 24/7** - Polling automatique toutes les 15 sec
2. ✅ **Alertes instantanées** - Email critique en <1 sec
3. ✅ **Interface intuitive** - Dashboard web simple et efficace
4. ✅ **Scalabilité** - Supporte 100+ équipements
5. ✅ **Audit complet** - Historique intégral des événements
6. ✅ **Multi-utilisateurs** - Admin + Operators + Preferences
7. ✅ **Personnalisation** - Seuils configurables par équipement
8. ✅ **Logs centralisés** - Tous les événements archivés

### 📊 Recommandations de Présentation

1. **Kick-off (5 min)** → Diagramme "Vue Client"
   - Montrer flux métier principal
   - Insister sur automatisation

2. **Démo fonctionnelle (15 min)**
   - Live dashboard
   - Créer alerte de test
   - Montrer email reçu
   - Acquitter alerte

3. **Architecture (10 min)** → Diagramme "Architecture Système"
   - Expliquer stack technique
   - Rassurer sur scalabilité
   - Montrer résilience

4. **Questions/Discussions (5 min)**
   - Adresser besoins spécifiques
   - Clarifier limitations
   - Évaluer satisfaction

### 📌 Fichiers à Livrer au Client

```
📁 Présentation Client/
├── 📄 README.md (ce fichier)
├── 🎨 sequence_diagram_client_overview.puml ← À GÉNÉRER EN PNG/PDF
├── 🏗️ architecture_system.puml ← À GÉNÉRER EN PNG/PDF
└── 📊 [Autres diagrammes pour équipe dev]
```

### 🔧 Conversion PlantUML → PNG/PDF
```bash
# Installation Graphviz + PlantUML
choco install graphviz plantuml  # Windows
brew install graphviz plantuml   # macOS
apt install graphviz plantuml    # Linux

# Générer PNG (ideal pour web/email)
plantuml -Tpng sequence_diagram_client_overview.puml
plantuml -Tpng architecture_system.puml

# Générer PDF (idéal pour impression/rapport)
plantuml -Tpdf sequence_diagram_client_overview.puml
plantuml -Tpdf architecture_system.puml

# Résultats dans même répertoire
# ✅ sequence_diagram_client_overview.png
# ✅ architecture_system.png
# ✅ sequence_diagram_client_overview.pdf
# ✅ architecture_system.pdf
```

---

**Créé:** 2025-11-16  
**Projet:** Supervision Réseau via SNMP  
**Version:** 1.0  
**Auteur:** Équipe Développement
