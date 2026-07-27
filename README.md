# ha-freebox-caller-id

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
