# ha-freebox-caller-id

5.Donner le droit de lire les appels :Dans Freebox OS.Connectez-vous sur mafreebox.freebox.fr. Allez dans Paramètres > Gestion des accès > Applications, éditez HA CallerID et cochez absolument Accès au journal d'appels.


alias: "Freebox - Action sur Appel Entrant"
description: "Se déclenche instantanément dès que le téléphone fixe sonne"
trigger:
  - platform: event
    event_type: freebox_incoming_call
action:
  # 1. Envoie une notification mobile
  - action: notify.notify
    data:
      title: "📞 Appel entrant Freebox !"
      message: "Appel de {{ trigger.event.data.name }} ({{ trigger.event.data.number }})"

  # 2. Exemple d'action supplémentaire : pause du lecteur multimédia
  - action: media_player.media_pause
    target:
      entity_id: media_player.salon

> Données disponibles dans trigger.event.data :
> 
> {{ trigger.event.data.number }} : Numéro de téléphone de l'appelant.
> {{ trigger.event.data.name }} : Nom associé dans le répertoire (ou "Inconnu").
> {{ trigger.event.data.id }} : Identifiant unique de l'appel Freebox.

alias: "Freebox - Baisse du son pendant la sonnerie"
trigger:
  - platform: state
    entity_id: binary_sensor.sonnerie_freebox
    to: "on"
action:
  # Action 1: On met la musique en pause quand ça commence à sonner
  - service: media_player.media_pause
    target:
      entity_id: media_player.salon
  
  # Action 2: On annonce qui appelle sur l'enceinte
  - service: tts.speak
    target:
      entity_id: tts.google_en_com
    data:
      media_player_entity_id: media_player.salon
      message: "Appel entrant de {{ state_attr('binary_sensor.sonnerie_freebox', 'caller_name') }}"
      
  # Action 3: On attend que la sonnerie s'arrête (décroché ou manqué)
  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.sonnerie_freebox
        to: "off"
        
  # Action 4: On remet la musique
  - service: media_player.media_play
    target:
      entity_id: media_player.salon
