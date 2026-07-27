![Freebox Caller ID for Home Assistant](/logo.png)
# Freebox Caller ID - Intégration pour Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-1.1.0-green.svg)](https://github.com/)

> # :warning: !! WORK IN PROGRESS !! :warning:

**Freebox Caller ID** est une intégration personnalisée pour Home Assistant permettant de détecter **en temps réel** les appels téléphoniques entrants sur la ligne fixe de votre Freebox, sans ajout de matériel supplémentaire.

*Inspiré de [https://github.com/jystervinou/freebox-caller-id](https://github.com/jystervinou/freebox-caller-id)*

*Largement fait avec l'IA*

---

## 📌 Objectif

Par défaut, l'API Freebox OS n'émet aucun push lorsqu'un téléphone sonne. Cependant, la Freebox inscrit immédiatement l'appel entrant dans son registre (`/api/v4/call/log/`) dès la première sonnerie avec une durée égale à `0`. 

Cette intégration effectue un scan HTTP rapide et asynchrone (polling toutes les 2 secondes par défaut) pour :
1. Déclencher un **événement natif** (`freebox_incoming_call`) dès le premier signal de sonnerie.
2. Activer un **capteur binaire** (`binary_sensor.sonnerie_freebox`) pendant toute la durée où le téléphone sonne, avec les informations de l'appelant.
3. Conserver les données de l'appelant dans un **capteur dédié** (`sensor.dernier_appel_freebox`), et l'historique des 10 derniers appels.
4. Fonctionner en **local**, sans cloud
5. Gérer de manière transparente les redémarrages de la Freebox grâce à un algorithme de **reconnexion progressive (*exponential backoff*)** pour ne pas polluer les journaux de Home Assistant.

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
```

---

## 🧩 Installation

### Installation via HACS
1. Ouvrir **HACS**  
2. Cliquer sur **Ajouter un dépôt personnalisé**  
3. Ajouter : https://github.com/MadMatt34/ha-freebox-caller-id
4. Choisir la catégorie **Intégration**  
6. Redémarrer Home Assistant

### Installation manuelle
1. Copiez le dossier `freebox_caller_id` dans `/config/custom_components/`.
2. Redémarrez Home Assistant pour faire détecter la nouvelle intégration.

---

## 🚀 Configuration de l'intégration

L'installation se fait **100 % via l'interface graphique** de Home Assistant.

### Étape 1 : Ajout de l'intégration dans Home Assistant
1. Dans Home Assistant, allez dans **Paramètres** > **Appareils et services**.
2. Cliquez sur **Ajouter une intégration** (en bas à droite).
3. Recherchez **Freebox Caller ID** et sélectionnez-le.
4. Laissez l'adresse IP / hôte par défaut (`mafreebox.freebox.fr`) et validez.

### Étape 2 : Validation physique sur le Freebox Server
1. L'assistant vous demande d'accorder l'autorisation.
2. Rendez-vous devant votre boîtier **Freebox Server** (physiquement).
3. Appuyez sur la **flèche de droite** (ou la touche de validation) sur l'écran tactile du boîtier pour accepter la demande **HA CallerID**.
4. Revenez sur Home Assistant et cliquez sur **Soumettre**.

### Étape 3 : Autorisation dans l'interface Freebox OS
1. Connectez-vous sur votre espace Freebox OS : [http://mafreebox.freebox.fr](http://mafreebox.freebox.fr).
2. Allez dans **Paramètres de la Freebox** > **Gestion des accès** > Onglet **Applications**.
3. Cliquez sur la ligne **HA CallerID**.
4. Cochez la case **Accès au journal d'appels**.
5. Enregistrez.

---

## ⚙️ Options de configuration UI

Vous pouvez ajuster l'intervalle de vérification à tout moment :
1. Allez dans **Paramètres** > **Appareils et services**.
2. Sur la carte **Freebox Caller ID**, cliquez sur le bouton **Configurer**.
3. Choisissez la fréquence de balayage (entre 1 et 60 secondes, 2s recommandé) et validez. L'intégration se rechargera automatiquement.

---

## 📡 Événements et Entités créés

### 1. Événement Home Assistant : `freebox_incoming_call`
Émis instantanément à l'arrivée de la première sonnerie d'un nouvel appel.

**Données transmises dans `trigger.event.data` :**
- `id` : Identifiant unique de l'appel Freebox.
- `number` : Numéro de téléphone de l'appelant.
- `name` : Nom de l'appelant (s'il est présent dans le répertoire Freebox) ou `"Inconnu"`.
- `type` : Type d'appel (`missed`, `accepted`, etc.).
- `datetime` : Horodatage UNIX / timestamp.

---

### 2. Capteur binaire : `binary_sensor.freebox_ringing`
- **Device Class** : `sound`
- **État** :
    - `on` : Pendant que le téléphone sonne.
    - `off` : Quand décroché ou après un délai d'attente maximum de 45s.
- **Attributs enrichis :**
  - `caller_name` : Nom du correspondant.
  - `caller_number` : Numéro de téléphone.
  - `call_datetime` : Horodatage de l'appel.
  - `call_type` : Type d'appel.

---

### 3. Capteur : `sensor.freebox_last_call`
- **État** : Nom ou numéro du dernier appelant enregistré.
- **Attributs enrichis :** Liste des 10 derniers appels avec les informations suivantes
  - `number` : Numéro du correspondant.
  - `name` : Nom associé dans le répertoire.
  - `type` : Type de l'appel.
  - `duration` : Durée de communication en secondes.
  - `timestamp` : Date/Heure de réception.

---

## 🤖 Exemples d'automatisations YAML

### Exemple 1 : Notification mobile et annonce vocale TTS
Déclenchement instantané à la réception d'un appel :

```yaml
alias: "Freebox - Notification et TTS Appel Entrant"
description: "Notifie sur le smartphone et annonce le nom du correspondant sur l'enceinte du salon"
trigger:
  - platform: event
    event_type: freebox_incoming_call
action:
  # Notification Push Mobile
  - action: notify.notify
    data:
      title: "📞 Appel fixe Freebox"
      message: "Appel entrant de {{ trigger.event.data.name }} ({{ trigger.event.data.number }})"

  # Annonce vocale sur enceinte connectée
  - action: tts.speak
    target:
      entity_id: tts.google_fr_fr
    data:
      media_player_entity_id: media_player.salon_speaker
      message: "Appel téléphonique entrant de {{ trigger.event.data.name }}"
```

---

### Exemple 2 : Pause multimédia automatique et reprise après la sonnerie
Met en pause le lecteur multimédia pendant toute la durée de la sonnerie et reprend la lecture une fois l'appel décroché ou abandonné :

```yaml
alias: "Freebox - Pause Musique / TV sur Sonnerie"
description: "Gère la mise en pause et la reprise des médias pendant qu'un appel sonne"
trigger:
  - platform: state
    entity_id: binary_sensor.freebox_ringing
    to: "on"
action:
  # 1. Mise en pause de la TV ou enceinte
  - action: media_player.media_pause
    target:
      entity_id: media_player.salon_tv

  # 2. Attente de la fin de la sonnerie (passage du capteur à 'off')
  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.freebox_ringing
        to: "off"

  # 3. Reprise de la lecture
  - action: media_player.media_play
    target:
      entity_id: media_player.salon_tv
```

---

### Exemple 3 : Affichage des derniers appels reçus
Une carte d'historique sur votre tableau de bord Home Assistant en utilisant une carte Markdown :

```yaml
type: markdown
title: "📜 Historique des derniers appels Freebox"
content: >
  {% set calls = state_attr('sensor.freebox_last_call', 'calls') %}
  | Nom / Numéro | Type | Durée |
  | :--- | :--- | :--- |
  {% for call in calls %}
  | **{{ call.name }}** <br><sub>{{ call.number }}</sub> | {{ call.type }} | {{ call.duration }}s |
  {% endfor %}
```

---

## 🛡️ Gestion des Erreurs

En cas de redémarrage de la Freebox ou de mise à jour du firmware :
- Un avertissement unique est inscrit dans les journaux de Home Assistant lors de la perte de communication.
- L'intégration bascule en mode **Backoff Exponentiel** (`2s -> 4s -> 8s -> 16s -> 32s -> 60s`).
- Dès le retour en ligne de la Freebox, la session est automatiquement ré-authentifiée et l'intervalle de balayage d'origine est rétabli, sans nécessiter de redémarrage de Home Assistant.

---

## 🛠️ Dépannage

- Vérifiez que votre Freebox est accessible sur le réseau local
- Assurez-vous que Home Assistant peut communiquer avec la Freebox
- Consultez les logs : **Paramètres → Système → Journaux**
