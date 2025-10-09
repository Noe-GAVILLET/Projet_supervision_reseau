# Projet de supervision réseau via SNMP

## Contexte
Ce projet a été réalisé dans le cadre d’un module de 32 heures.  
L’objectif est de développer une application de **supervision réseau** permettant de surveiller un parc de matériels hétérogènes (serveurs, routeurs, switchs, etc.) à l’aide du protocole **SNMP**.

---

## Objectifs
L’application doit permettre :
- La **surveillance en ligne** du parc avec affichage textuel et graphique.
- La **sauvegarde des mesures** dans une base de données.
- La **gestion des alertes** grâce à des seuils configurables.
- La **gestion des défaillances** avec enregistrement dans des logs.
- La possibilité de définir des **modèles de supervision** adaptés à chaque type d’équipement (serveur web, serveur de fichiers, routeur, switch...).

---

## Architecture
L’application est découpée en plusieurs modules :

1. **Module Configuration (Flask UI)**  
   - Ajouter, éditer, supprimer des équipements.  
   - Import/export configuration JSON ou XML.  
   - Gestion des modèles de supervision (templates OID).  

2. **Module Base de données (SQLite/SQLAlchemy)**  
   - Stockage des équipements, métriques, mesures et alertes.  
   - Schéma simple, extensible pour différents types d’équipements.  

3. **Module Poller SNMP**  
   - Collecte périodique des données via SNMP (pysnmp).  
   - Gestion des timeouts et retries.  
   - Détection des équipements inaccessibles.  

4. **Module Alerte / Notification**  
   - Comparaison des mesures avec les seuils.  
   - Génération d’alertes (warning/critical).  
   - Historisation des événements.  

5. **Module Visualisation / Graphiques**  
   - Affichage en temps réel et historique des mesures.  
   - Graphiques interactifs (Chart.js / Plotly).  
   - Export CSV/JSON.  

---

## Technologies utilisées
- **Langage principal :** Python 3.x  
- **Framework web :** Flask (backend + Jinja2)  
- **Base de données :** SQLite (MVP) / PostgreSQL (optionnel)  
- **ORM :** SQLAlchemy  
- **SNMP :** pysnmp  
- **Planification :** schedule / APScheduler  
- **Graphiques :** Matplotlib, Plotly ou Chart.js  
- **Frontend :** HTML5 / CSS3 / Bootstrap  

---

## Organisation du projet


```mermaid
gantt
    dateFormat  YYYY-MM-DD
    title Supervision de matériel réseau via SNMP
    Analyse et conception : 0, 2025-09-15, 1d
    Analyse du cahier des charges : 9, 2025-09-15, 1d
    Listing des cas d’usage : 12, 2025-09-15, 1d
    Spécifications fonctionnelles : 11, 2025-09-15, 1d
    Diagrammes UML : 10, 2025-09-15, 1d
    Module de configuration : 1, 2025-09-17, 1d
    Création structure projet : 13, 2025-09-17, 1d
    Gestion configuration JSON/XML : 14, 2025-09-17, 1d
    Création site web Flask : 15, 2025-09-17, 1d
    Création module Ajout / suppression / édition équipements : 17, 2025-09-17, 1d
    Création module Ajout / suppression / édition de collecteur : 18, 2025-09-17, 1d
    Module de surveillance : 2, 2025-09-25, 1d
    Implémentation SNMP Poller : 20, 2025-09-25, 1d
    Application modèles de supervision : 19, 2025-09-25, 1d
    Collecte et structuration des mesures : 21, 2025-09-25, 1d
    Création de graphique : 22, 2025-09-25, 1d
    Module de logs : 3, 2025-10-09, 1d
    Création base de données SQLite : 23, 2025-10-09, 1d
    Stockage des mesures SNMP : 24, 2025-10-09, 1d
    Stockage des alertes : 26, 2025-10-09, 1d
    Gestion des alertes : 4, 2025-10-16, 1d
    Création des seuils : 25, 2025-10-16, 1d
    Générateur d'alerte par mail : 27, 2025-10-16, 1d
    Affichage alerte sur la page web : 28, 2025-10-16, 1d
    Interface utilisateur : 5, 2025-10-24, 1d
    Graphiques temps réel : 33, 2025-10-24, 1d
    Affichage état détaillé équipement : 32, 2025-10-24, 1d
    Page d'authentification : 30, 2025-10-24, 1d
    Ajout navigation et filtre : 29, 2025-10-24, 1d
    Ajout de CSS/Java : 31, 2025-10-24, 1d
    Tests : 6, 2025-11-13, 1d
    Test d'utilisation (Admin/Opérateur) : 37, 2025-11-13, 1d
    Correction bugs et ajustements : 34, 2025-11-13, 1d
    Finalisation / Livrables : 8, 2025-11-27, 1d
    Rédaction manuel d’utilisation : 35, 2025-11-27, 1d
    Préparation soutenance : 36, 2025-11-27, 0d
```
