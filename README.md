readme_content = """# Freebox Caller ID Instant - Intégration Custom Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-1.1.0-green.svg)](https://github.com/)

**Freebox Caller ID Instant** est un composant personnalisé (*custom component*) pour Home Assistant permettant de détecter **en temps réel** les appels téléphoniques entrants sur la ligne fixe de votre Freebox, sans ajouter de matériel supplémentaire (comme un modem USB Caller ID).

---

## 📌 Objectif

Par défaut, l'API Freebox OS n'émet pas de push WebSocket lorsqu'un téléphone sonne. Cependant, la Freebox inscrit immédiatement l'appel entrant dans son registre (`/api/v4/call/log/`) dès la première sonnerie avec une durée égale à `0`. 

Cette intégration effectue un balayage HTTP rapide et asynchrone (polling toutes les 2 secondes par défaut) pour :
1. Déclencher un **événement natif** (`freebox_incoming_call`) dès le premier signal de sonnerie.
2. Activer un **capteur binaire** (`binary_sensor.sonnerie_freebox`) pendant toute la durée où le téléphone sonne.
3. Conserver les données de l'appelant dans un **capteur dédié** (`sensor.dernier_appel_freebox`).
4. Gérer de manière transparente les redémarrages de la Freebox grâce à un algorithme de **reconnexion progressive (*exponential backoff*)** pour ne pas polluer les journaux de Home Assistant.

---

## 🛠️ Structure des fichiers

Dans votre dossier Home Assistant `/config/custom_components/freebox_caller_id/`, assurez-vous d'avoir l'arborescence suivante :

```text
config/
└── custom_components/
    └── freebox_caller_id/
        ├── __init__.py
        ├── binary_sensor.py
        ├── config_flow.py
        ├── const.py
        ├── manifest.json
        ├── sensor.py
        └── translations/
            └── fr.json
