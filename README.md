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
    title Supervision de matériel réseau via SNMP (état au 22/11/2025)

    section Analyse_et_conception
    Analyse_et_conception                 :done, ac, 2025-09-15, 1d
    Analyse_du_cahier_des_charges         :done, adc, 2025-09-15, 1d
    Listing_des_cas_d_usage               :done, lcu, 2025-09-15, 1d
    Specifications_fonctionnelles         :done, sf, 2025-09-15, 1d
    Diagrammes_UML                        :done, uml, 2025-09-15, 1d

    section Module_de_configuration
    Module_de_configuration               :done, mc, 2025-09-17, 1d
    Creation_structure_projet             :done, csp, 2025-09-17, 1d
    Gestion_configuration_JSON_XML        :done, gcj, 2025-09-17, 1d
    Creation_site_web_Flask               :done, flask, 2025-09-17, 1d
    Creation_module_Ajout_suppr_equipements :done, equipt, 2025-09-17, 1d
    Creation_module_Ajout_suppr_collecteur  :done, coll, 2025-09-17, 1d

    section Module_de_surveillance
    Module_de_surveillance                :done, ms, 2025-09-25, 1d
    Implementation_SNMP_Poller            :done, snmp, 2025-09-25, 1d
    Application_modeles_de_supervision    :done, msup, 2025-09-25, 1d
    Collecte_et_structuration_des_mesures :done, csm, 2025-09-25, 1d
    Creation_de_graphique                 :done, graph, 2025-09-25, 1d

    section Module_de_logs
    Module_de_logs                        :done, log, 2025-10-09, 1d
    Creation_base_de_donnees_SQLite       :done, bdd, 2025-10-09, 1d
    Stockage_des_mesures_SNMP             :done, stsnmp, 2025-10-09, 1d
    Stockage_des_alertes                  :done, stal, 2025-10-09, 1d

    section Gestion_des_alertes
    Gestion_des_alertes                   :done, ga, 2025-10-16, 1d
    Creation_des_seuils                   :done, seuil, 2025-10-16, 1d
    Generateur_alerte_par_mail            :done, mail, 2025-10-16, 1d
    Affichage_alerte_sur_la_page_web      :done, alertw, 2025-10-16, 1d

    section Interface_utilisateur
    Interface_utilisateur                 :done, iu, 2025-10-24, 1d
    Graphiques_temps_reel                 :done, gtr, 2025-10-24, 1d
    Affichage_etat_detaille_equipement    :done, etat, 2025-10-24, 1d
    Page_authentification                 :done, auth, 2025-10-24, 1d
    Ajout_navigation_et_filtre            :done, nav, 2025-10-24, 1d
    Ajout_de_CSS_Java                     :done, css, 2025-10-24, 1d

    section Tests
    Tests                                 :done, tests, 2025-11-13, 1d
    Test_utilisation_Admin_Operateur      :done, testuse, 2025-11-13, 1d
    Correction_bugs_et_ajustements        :done, corr, 2025-11-13, 1d

    section Finalisation_Livrables
    Finalisation_Livrables                :fin, 2025-11-27, 1d
    Redaction_manuel_utilisation          :fin, 2025-11-27, 1d
    Preparation_soutenance                :fin, 2025-11-27, 0d

    section Examen
    Examen                                :exam, 2025-12-04, 1d
```
