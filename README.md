# Freebox Caller ID - Home Assistant Integration

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Component-blue.svg)](https://www.home-assistant.io/)
[![Latest Release](https://img.shields.io/github/v/release/MadMatt34/ha-freebox-caller-id?color=green)](https://github.com/MadMatt34/ha-freebox-caller-id/releases)

![Freebox Caller ID for Home Assistant](https://github.com/MadMatt34/ha-freebox-caller-id/blob/main/logo.png)

[🇫🇷 README en FRANCAIS 🇫🇷](https://github.com/MadMatt34/ha-freebox-caller-id/blob/main/README.fr.md)

**Freebox Caller ID** is a custom Home Assistant integration designed to detect incoming calls on your [Freebox](https://www.free.fr/freebox) landline **in real-time**, without requiring any additional hardware.

---

## 📌 Goal

By default, the [Freebox OS API](https://dev.freebox.fr/sdk/os/) does not send push notifications when a phone rings. However, the Freebox immediately registers incoming calls in its call log (`/api/v4/call/log/`) upon the very first ring with a duration of `0`.

This integration performs fast, asynchronous HTTP polling (every 2 seconds by default) to:
- Fire a **native event** (`freebox_incoming_call`) on the first ring signal.
- Turn on a **binary sensor** (`binary_sensor.area_freebox_phone_xxxxxx_ringing`) while the phone is ringing, enriched with caller information.
- Store the caller's details in a **dedicated sensor** (`sensor.area_freebox_phone_xxxxxx_last_call`), alongside a history of the last 10 calls.
- Work **100% locally** without any cloud dependency.
- Smoothly handle Freebox reboots using an **exponential backoff** algorithm to avoid flooding Home Assistant log files.

---

## 🛠️ File Structure

In your Home Assistant `/config/custom_components/freebox_caller_id/` directory, ensure you have the following file layout:

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
            ├── en.json
            └── fr.json
```

---

## 🧩 Installation

### Option 1: HACS Installation (Recommended)
1. Open **HACS** in Home Assistant.
2. Click **Custom Repositories** (top right menu).
3. Add: `https://github.com/MadMatt34/ha-freebox-caller-id`
4. Select category: **Integration**.
5. Click **Add**, then find and download **Freebox Caller ID**.
6. Restart Home Assistant.

### Option 2: Manual Installation
1. Copy the `freebox_caller_id` folder into your `/config/custom_components/` directory.
2. Restart Home Assistant to detect the new integration.

---

## 🚀 Integration Setup

Setup is performed **100% via the Home Assistant User Interface**.

### Step 1: Add the integration in Home Assistant
1. In Home Assistant, go to **Settings** > **Devices & Services**.<br>
   or click [![Open your Home Assistant instance and show your integrations.](https://my.home-assistant.io/badges/integrations.svg)](https://my.home-assistant.io/redirect/integrations/)
2. Click **Add Integration** (bottom right).
3. Search for **Freebox Caller ID** and select it.
4. Leave the default IP/Host (`mafreebox.freebox.fr`) and validate.

### Step 2: Physical approval on the Freebox Server
1. The setup wizard will prompt you for physical authorization.
2. Walk to your physical **Freebox Server** box.
3. Press the **Right Arrow** (or validation button) on the touch screen to accept the **HA CallerID** request.
4. Return to Home Assistant and click **Submit**.

### Step 3: Grant permissions in Freebox OS
1. Log in to your Freebox OS web interface: [http://mafreebox.freebox.fr](http://mafreebox.freebox.fr).
2. Go to **Freebox Settings** > **Access Management** > **Applications** tab.
3. Click on **HA CallerID**.
4. Check the box for **Access to call log** (*Accès au journal d'appels*).
5. Click **Save**.

---

## ⚙️ Configuration Options

You can adjust some settings at any time:
1. Go to **Settings** > **Devices & Services**.
2. On the **Freebox Caller ID** card, click **Configure**.
3. Change the settings:
   - Polling frequency : **Scan interval** (between 1 and 60 seconds; 2 seconds recommended and as default)
   - Active ring timeout : **Maximum ringing duration** (between 1 and 180 seconds; 45 seconds as default)
4. Save. The integration will reload automatically.

---

## 📡 Events and Entities

### 1. Home Assistant Event: `freebox_incoming_call`
Fired instantaneously as soon as a new incoming call starts ringing.

**Event payload in `trigger.event.data`:**
- `id`: Unique identifier for the Freebox call.
- `number`: Caller's phone number.
- `name`: Caller's name (if saved in the Freebox phonebook) or `"Unknown"`.
- `type`: Call type (`missed`, `accepted`, etc.).
- `datetime`: UNIX timestamp of the call.

---

### 2. Binary Sensor: `binary_sensor.area_freebox_phone_xxxxxx_ringing`
- **Device Class**: `sound`
- **State**:
    - `on`: While the phone is ringing.
    - `off`: When answered or after a maximum timeout of 45 seconds.
- **Attributes:**
  - `caller_name`: Name of the caller.
  - `caller_number`: Phone number.
  - `call_datetime`: Timestamp of the call.
  - `call_type`: Call type.

---

### 3. Sensor: `sensor.area_freebox_phone_xxxxxx_last_call`
- **State**: Name or phone number of the last recorded caller.
- **Attributes:** List of the last 10 calls with the following details:
  - `number`: Phone number.
  - `name`: Associated name in the contacts list.
  - `type`: Type of call.
  - `duration`: Call duration in seconds.
  - `timestamp`: Date/Time received.

---

## 🤖 Automations and Dashboard Examples

### Example 1: Mobile Notification and Voice TTS Announcement
Triggers instantly when an incoming call arrives:

```yaml
alias: "Freebox - Incoming Call Notification and TTS"
description: "Notifies smartphone and announces caller name on the living room speaker"
trigger:
  - platform: event
    event_type: freebox_incoming_call
action:
  # Mobile Push Notification
  - action: notify.notify
    data:
      title: "📞 Freebox Landline Call"
      message: "Incoming call from {{ trigger.event.data.name }} ({{ trigger.event.data.number }})"

  # Voice announcement on connected speaker
  - action: tts.speak
    target:
      entity_id: tts.google_en_com
    data:
      media_player_entity_id: media_player.living_room_speaker
      message: "Incoming phone call from {{ trigger.event.data.name }}"
```

---

### Example 2: Automatic Media Pause and Resume on Ringing
Pauses media playback while the phone is ringing and resumes playing once answered or stopped:

```yaml
alias: "Freebox - Pause/Resume Media on Ringing"
description: "Handles media playback pause and resume during ringing phone calls"
trigger:
  - platform: state
    entity_id: binary_sensor.area_freebox_phone_xxxxxx_ringing
    to: "on"
action:
  # 1. Pause TV or speaker
  - action: media_player.media_pause
    target:
      entity_id: media_player.living_room_tv

  # 2. Wait until phone stops ringing (sensor turns 'off')
  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.area_freebox_phone_xxxxxx_ringing
        to: "off"

  # 3. Resume playback
  - action: media_player.media_play
    target:
      entity_id: media_player.living_room_tv
```

---

### Example 3: Recent Call History Dashboard Card
A call history table for your Home Assistant dashboard using Markdown + Card-Mod:

```yaml
type: markdown
content: >
  {%- set calls = state_attr('sensor.area_freebox_phone_xxxxxx_last_call',
  'calls') -%}
  | | Name | Number | Date | Duration |
  
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

### Example 4: Animated Incoming Call Card
An animated tile card that appears when the phone rings (uses Tile Card + Card-Mod):

```yaml
type: tile
entity: binary_sensor.area_freebox_phone_xxxxxx_ringing
name: "Ringing: Incoming Call"
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

## 🛡️ Error Handling

If your Freebox reboots or undergoes a firmware update:
- A single warning log is logged in Home Assistant when communication is lost.
- The integration enters **Exponential Backoff** mode (`2s -> 4s -> 8s -> 16s -> 32s -> 60s`).
- Once the Freebox comes back online, the session automatically re-authenticates and restores the original polling interval without requiring a Home Assistant restart.

---

## 🛠️ Troubleshooting

- Verify that your Freebox is accessible on your local network.
- Ensure Home Assistant can reach the Freebox host IP.
- Check logs: **Settings → System → Logs**.
- Diagnostics & Privacy: You can safely export diagnostic files when opening an issue on GitHub. Access tokens, credentials, and sensitive personal data (such as phone numbers and contact names) are automatically anonymized.

---

### CREDITS
*Inspired by [https://github.com/jystervinou/freebox-caller-id](https://github.com/jystervinou/freebox-caller-id) and largely built with AI support.*
