# Comfortzone RX95 - Project Knowledge & Memory

## Project Description
The goal of this project is to control a Comfortzone RX95 exhaust air heat pump via Home Assistant. The heat pump handles both hot water preparation and heating for the water-borne underfloor heating system, but it only has a single 3.5 kW compressor and can therefore only perform one task at a time.

Version 2.0 aims to:
1. Package the project neatly for GIT and HACS.
2. Optimize API calls and handle delays more intelligently using an internal command queue.
3. Establish robust documentation for future development.
4. Provide a premium, intuitive Config Flow (setup process) in Home Assistant.

## Technical Specifications (RX95)
- **Max Heat Pump Capacity:** 3.5 kW (Max heating capacity: 9.5 kW with addition)
- **Addition Heater (Electric coil):** 6.0 kW
- **Tank Volume:** 170 L
- **Refrigerant:** R32 (720g - 950g depending on task)
- **Max Flow Line Temperature:** 70°C
- **Hot Water Temperature (Adjustable):** 50-60 °C

## Known Issues and Learnings
- **API Performance:** The API is slow when executing multiple write operations simultaneously. The previous solution involved inserting `delay: 00:00:05` between each operation in Home Assistant automations. For v2.0, this is solved by an internal asynchronous queue in `api.py`.
- **Single Compressor Limitation:** Since the compressor can only do one thing at a time, prioritizing between hot water and house heating must be managed carefully, especially during high load (e.g., cold winter nights).

## Development Decisions (Version 2.0)
- **Language Policy:** All code, comments, documentation, and filenames must be strictly in English.
- **HACS Structure:** Integration files are placed in `custom_components/comfortzone_rx95/`.
- **API Delay Handling:** Implemented an asynchronous queue mechanism in the API client to ensure sequential command execution with a safety delay, eliminating the need for `delay` actions in Home Assistant automations.
