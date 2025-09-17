# Documentation de l'Environnement de Travail

## Introduction

Cette documentation décrit l'environnement de travail mis en place pour la gestion d'une base de données MySQL sur une machine virtuelle (VM) Debian 13. L'objectif principal est de déployer un conteneur Docker exécutant MySQL.

## Détails de la Machine Virtuelle (VM)

- **Système d'exploitation** : Debian 13
- **Processeur** : 4 cœurs
- **Mémoire vive (RAM)** : 4 Go

## Configuration SSH avec Clé Privée

Pour sécuriser l'accès à la machine virtuelle, nous avons configuré l'authentification SSH par clé privée.

### Étapes pour configurer SSH avec clé privée

1. **Génération de la clé SSH** :
   Sur votre machine locale, ouvrez un terminal et générez une paire de clés SSH avec la commande suivante :

   ```bash
   ssh-keygen -t rsa -b 4096 -C "votre_email@example.com"
