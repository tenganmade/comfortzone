# Comfortzone Heat Pump - Lovelace Dashboards

Here are some premium Lovelace YAML cards you can add to your Home Assistant dashboard. We recommend using **Mushroom Cards** and **Mini Graph Card** (available via HACS) for the best visual experience, but they degrade gracefully or you can adapt them to standard cards.

## 1. Main Overview (Thermostat & Core Sensors)
A sleek, compact view of your indoor climate and hot water status.

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-climate-card
    entity: climate.comfortzone_heat_pump_climate
    show_temperature_control: true
    collapsible_controls: true
    name: Indoor Climate
    icon: mdi:home-thermometer
  
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: sensor.comfortzone_indoor_temp_te3
        name: Indoor
        icon: mdi:thermometer
        icon_color: orange
      - type: custom:mushroom-entity-card
        entity: sensor.comfortzone_outdoor_temp_te0
        name: Outdoor
        icon: mdi:pine-tree
        icon_color: blue
  
  - type: custom:mushroom-entity-card
    entity: sensor.comfortzone_hot_water_temp_te24
    name: Hot Water Status
    icon: mdi:water-boiler
    icon_color: red
    secondary_info: state
```

## 2. "Under the Hood" - Technical Details
Perfect for a sub-view to monitor the compressor, power usage, and alarms.

```yaml
type: vertical-stack
cards:
  - type: custom:mini-graph-card
    name: Power Usage (Compressor + Addition)
    icon: mdi:flash
    entities:
      - entity: sensor.comfortzone_compressor_effect
        name: Compressor
        color: "#4caf50"
      - entity: sensor.comfortzone_addition_effect
        name: Addition (Coil)
        color: "#f44336"
    hours_to_show: 24
    points_per_hour: 4
    show:
      labels: true
      fill: true

  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: binary_sensor.comfortzone_compressor_active
        name: Compressor
        icon: mdi:engine
      - type: custom:mushroom-entity-card
        entity: binary_sensor.comfortzone_filter_alarm
        name: Filter Status
        icon: mdi:air-filter

  - type: entities
    title: System Sensors
    entities:
      - entity: sensor.comfortzone_flow_line_temp_te1
        name: Flow Line Temp
      - entity: sensor.comfortzone_return_temp_te2
        name: Return Temp
      - entity: sensor.comfortzone_exhaust_air_temp_te7
        name: Exhaust Temp
```

## 3. Options Flow
Don't forget! You can now change the **Heat Pump Model** at any time. 
Go to **Settings -> Devices & Services -> Comfortzone Heat Pump -> Configure** to access the Options Flow and change models.
