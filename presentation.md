**Linguabridge — Projektübersicht**

Kurzbeschreibung
- Linguabridge ist eine modulare Webanwendung, die gesprochene Eingaben in Echtzeit oder aus Audiodateien entgegennimmt, automatisch transkribiert, kontextbewusst übersetzt und als natürliche Sprachausgabe zurückgibt. Ziel ist eine zuverlässige, latenzarme Sprachbrücke für mehrsprachige Kommunikation und Integrationen.

Funktionsweise (High-Level)
- Aufnahme / Streaming: Der Client überträgt Audio per WebSocket oder HTTP-Upload an das Backend.
- Speech-to-Text (STT): Ein Streaming-fähiger STT-Dienst (Client-Integration) wandelt Audio in Text.
- Übersetzung: Der erkannte Text wird an eine Übersetzungs-/LLM-API gesendet, die kontextuelle Anpassungen und Sprachstil vornimmt.
- Text-to-Speech (TTS): Der übersetzte Text wird an einen TTS-Service übergeben, der natürliche Stimmen ausgibt.
- Rückgabe: Die erzeugte Audiodatei bzw. der Stream wird an den Client zurückgespielt.

Architektur & Komponenten
- Frontend: Einfache SPA (HTML + JavaScript) für Aufnahme, Steuerung und Wiedergabe.
- Backend: Python-ASGI-Anwendung (ausgeführt mit `uvicorn`) für Routing, WebSockets und Orchestrierung.
- STT-Modul: Integration zu Streaming-fähigen STT-Anbietern (z. B. Deepgram).
- Übersetzungsmodul: Integration zu LLM-/Übersetzungs-APIs (z. B. OpenAI) für kontextbewusste Übersetzungen.
- TTS-Modul: Hochwertige TTS-Provider (z. B. ElevenLabs) für natürliche Stimmen.

Eingesetzte Technologien (Kurz)
- Backend: Python
- Server: ASGI / `uvicorn`
- STT: Deepgram-Streaming (oder vergleichbar)
- Übersetzung: MyMemory.translated.net free API
- TTS: ElevenLabs-API (oder vergleichbare Anbieter)
- Frontend: HTML, JavaScript
- Konfiguration: Umgebungsvariablen für Secrets und API-Schlüssel

Betrieb & Sicherheit
- Secrets und API-Schlüssel werden außerhalb des Repos (Umgebungsvariablen / Secret Manager) verwaltet.
- Produktivbetrieb benötigt HTTPS, CORS-Konfiguration und Authentifizierung für Streaming-Endpunkte.
- Datenschutz: Für sensible Daten sind On-Prem-Optionen oder hybride Modelle empfehlenswert.

Erweiterungsmöglichkeiten
- SSML-Unterstützung, Stimmenauswahl und Feintuning des TTS.
- Batch-Verarbeitung, Persistenz und Nachbearbeitung (Transkript-Editor).
- On-Premise-Modelle für streng regulierte Umgebungen.

Kurzfazit
- Linguabridge bietet eine modulare, erweiterbare Pipeline für Echtzeit- und asynchrone Sprachübersetzung. Die klare Trennung der Komponenten erlaubt einfachen Austausch von Diensten, gezielte Optimierung der Latenz und ein sicheres Produktions-Deployment.
