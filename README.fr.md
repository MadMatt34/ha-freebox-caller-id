# Freebox Caller ID - Intégration pour Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-blue.svg)](https://www.home-assistant.io/)
[![Latest Release](https://img.shields.io/github/v/release/MadMatt34/ha-freebox-caller-id?color=green)](https://github.com/MadMatt34/ha-freebox-caller-id/releases)

![Freebox Caller ID for Home Assistant](https://github.com/MadMatt34/ha-freebox-caller-id/blob/main/logo.png)

[🏴󠁧󠁢󠁥󠁮󠁧󠁿 README in ENGLISH 🏴󠁧󠁢󠁥󠁮󠁧󠁿](https://github.com/MadMatt34/ha-freebox-caller-id/blob/main/README.md)

**Freebox Caller ID** est une intégration personnalisée pour Home Assistant permettant de détecter **en temps réel** les appels téléphoniques entrants sur la ligne fixe de votre [Freebox](https://www.free.fr/freebox), sans ajout de matériel supplémentaire.

---

## 📌 Objectif

Par défaut, l'[API Freebox OS](https://dev.freebox.fr/sdk/os/) n'émet aucun push lorsqu'un téléphone sonne. Cependant, la Freebox inscrit immédiatement l'appel entrant dans son registre (`/api/v4/call/log/`) dès la première sonnerie avec une durée égale à `0`. 

Cette intégration effectue un scan HTTP rapide et asynchrone (polling toutes les 2 secondes par défaut) pour :
1. Déclencher un **événement natif** (`freebox_incoming_call`) dès le premier signal de sonnerie.
2. Activer un **capteur binaire** (`binary_sensor.piece_freebox_phone_xxxxxx_sonnerie`) pendant toute la durée où le téléphone sonne, avec les informations de l'appelant.
3. Conserver les données de l'appelant dans un **capteur dédié** (`sensor.piece_freebox_phone_xxxxxx_dernier_appel`), et l'historique des 10 derniers appels.
4. Fonctionner en **local**, sans cloud
5. Gérer de manière transparente les redémarrages de la Freebox grâce à un algorithme de **reconnexion progressive** (*exponential backoff*) pour ne pas polluer les journaux de Home Assistant.

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

### Option 1 : Installation via HACS (recommandée)
1. Ouvrir **HACS**  
2. Cliquer sur **Ajouter un dépôt personnalisé**  
3. Ajouter : https://github.com/MadMatt34/ha-freebox-caller-id
4. Choisir la catégorie **Intégration**  
6. Redémarrer Home Assistant

### Option 2 : Installation manuelle
1. Copiez le dossier `freebox_caller_id` dans `/config/custom_components/`.
2. Redémarrez Home Assistant pour faire détecter la nouvelle intégration.

---

## 🚀 Configuration de l'intégration

L'installation se fait **100 % via l'interface graphique** de Home Assistant.

### Étape 1 : Ajout de l'intégration dans Home Assistant
1. Dans Home Assistant, allez dans **Paramètres** > **Appareils et services**.
 [![Open your Home Assistant instance and show your integrations.](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/) 
3. Cliquez sur **Ajouter une intégration** (en bas à droite).
4. Recherchez **Freebox Caller ID** et sélectionnez-le.
5. Laissez l'adresse IP / hôte par défaut (`mafreebox.freebox.fr`) et validez.

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

## ⚙️ Modifier les options de configuration

Vous pouvez ajuster certains paramètres à tout moment :
1. Allez dans **Paramètres** > **Appareils et services**.
2. Sur la carte **Freebox Caller ID**, cliquez sur le bouton **Configurer**.
3. Modifiez les paramètres :
   - Intervalle de vérification : **Fréquence de scan** (entre 1 et 60 secondes, 2s recommandé et par défaut)
   - Durée de sonnerie active : **Durée maximale de la sonnerie** (entre 1 et 180 secondes, 45s par défaut)
5. Validez. L'intégration se rechargera automatiquement.

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

### 2. Capteur binaire : `binary_sensor.piece_freebox_phone_xxxxxx_sonnerie`
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

### 3. Capteur : `sensor.piece_freebox_phone_xxxxxx_dernier_appel`
- **État** : Nom ou numéro du dernier appelant enregistré.
- **Attributs enrichis :** Liste des 10 derniers appels avec les informations suivantes
  - `number` : Numéro du correspondant.
  - `name` : Nom associé dans le répertoire.
  - `type` : Type de l'appel.
  - `duration` : Durée de communication en secondes.
  - `timestamp` : Date/Heure de réception.

---

## 🤖 Exemples d'automatisations et dashboards

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
    entity_id: binary_sensor.piece_freebox_phone_xxxxxx_sonnerie
    to: "on"
action:
  # 1. Mise en pause de la TV ou enceinte
  - action: media_player.media_pause
    target:
      entity_id: media_player.salon_tv

  # 2. Attente de la fin de la sonnerie (passage du capteur à 'off')
  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.piece_freebox_phone_xxxxxx_sonnerie
        to: "off"

  # 3. Reprise de la lecture
  - action: media_player.media_play
    target:
      entity_id: media_player.salon_tv
```

---

### Exemple 3 : Affichage des derniers appels
Une belle carte d'historique sur votre tableau de bord Home Assistant en utilisant une carte Markdown + Card-Mod :

```yaml
type: markdown
content: >
  {%- set calls = state_attr('sensor.piece_freebox_phone_xxxxxx_dernier_appel',
  'calls') -%}
  | | Nom | Numéro | Date | Durée |
  
  | :--: | :--- | :--: | :--: | :--: |
  
  {% for call in calls -%}
    | <ha-icon icon="mdi:phone-{{- call.type | replace('accepted', 'incoming') -}}"></ha-icon> | **{{ call.name }}** | <a href="tel:{{ call.number }}">{{ call.number }}</a> | {{ call.timestamp | timestamp_custom("%d/%m %Hh%M") }} | {{ call.duration }}s |
  {% endfor %}
text_only: true
card_mod:
  style:
    ha-markdown $: |
      tr td:not(:first-child) {
        font-size: var(--ha-font-size-s);
      }
      tr td:nth-child(3) {
        font-family: digital;
        white-space: nowrap;
      }
      div {
        overflow-y: scroll !important;
        scrollbar-width: thin;
        height: 180px;
      }
      table {
        width: 100%;
        background: var(--card-background-color);
      }
      table > td {
        white-space: nowrap;
      }
      ha-icon {
        --mdc-icon-size: var(--ha-font-size-xl) !important;
      }
      ha-icon[icon="mdi:phone-missed"] {
        color: var(--error-color);
      }
      ha-icon[icon="mdi:phone-incoming"] {
        color: var(--warning-color);
      }
      ha-icon[icon="mdi:phone-outgoing"] {
        color: var(--success-color);
      }
```

---

### Exemple 4 : Affichage d'un appel entrant
Une belle carte pour apporter un visuel quand le téléphone sonne en utilisant une carte Tuile + Card-Mod :

```yaml
type: tile
entity: binary_sensor.piece_freebox_phone_xxxxxx_sonnerie
name: "Sonnerie : Appel entrant"
state_content:
  - caller_name
  - caller_number
tap_action:
  action: none
icon_tap_action:
  action: none
card_mod:
  style: |
    ha-state-icon {
      animation: hithere 0.75s infinite;
      color: var(--pink-color);
    }
    @keyframes hithere {
      30% { transform: scale(1.2); }
      40%, 60% { transform: rotate(-20deg) scale(1.2); }
      50% { transform: rotate(20deg) scale(1.2); }
      70% { transform: rotate(0deg) scale(1.2); }
      100% { transform: scale(1); }
    }
visibility:
  - condition: state
    state: "on"
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
- Diagnostics & Vie privée : Exportez vos fichiers de diagnostic en toute sécurité lors de l'ouverture d'un ticket sur GitHub ; vos jetons d'accès, identifiants et données personnelles (numéros de téléphone et noms des correspondants) sont automatiquement anonymisés.

---

### CREDITS
*Inspiré de [https://github.com/jystervinou/freebox-caller-id](https://github.com/jystervinou/freebox-caller-id) et largement fait avec l'IA*
