1. Mise en place du projet Flask

Créer une structure de base :

supervision/
├── app.py
├── config.py
├── requirements.txt
├── /templates
├── /static
├── /routes
├── /models
├── /services
└── /tests


app.py : point d’entrée (création de l’app Flask).

config.py : paramètres (DB, clé secrète, options).

requirements.txt : Flask, SQLAlchemy, pysnmp, etc.

------------

Interfaces Web (routes Flask)

/ : Tableau de bord (synthèse du parc, état des équipements).

/equipments : liste et gestion (CRUD).

/equipments/add : ajout via formulaire.

/metrics/<equipment_id> : détail et suivi des métriques.

/alerts : affichage des alertes en cours et historique.

/reports : export CSV/JSON.


-----------

Création de l'environnement virtuel : 

py -m venv .venv
.venv\Scripts\Activate.ps1
