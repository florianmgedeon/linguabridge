# LinguaBridge

LinguaBridge is a locally hosted web application (GitHub Codespaces + browser access via forwarded localhost URL) that translates between **German ↔ English** in near real-time.

This repo currently implements **PR 1** (full-stack scaffold + mic permission) and **PR 2** (real-time audio streaming over WebSocket). No AI logic yet.

---

## Project Structure

```
linguabridge/
├── backend/
│   ├── main.py           ← FastAPI server (HTTP + WebSocket)
│   └── requirements.txt  ← Python dependencies
├── frontend/
│   ├── index.html        ← Browser UI
│   └── app.js            ← Microphone, device, and streaming logic
└── README.md
```

---

## How to Run & Test (Beginner-Friendly Guide)

### Option A — GitHub Codespaces (recommended)

> Codespaces gives you a full Linux computer inside your browser. No local install needed.

1. **Open a Codespace**
   - On the repository page on GitHub, click the green **Code** button.
   - Choose the **Codespaces** tab → **Create codespace on main**.
   - Wait ~1 minute for it to start.

2. **Install Python dependencies**

   In the terminal at the bottom of the Codespace, run:

   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Start the backend server**

   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

   You should see output like:
   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```

4. **Forward port 8000**
   - Look at the **Ports** tab at the bottom of the Codespace (next to Terminal).
   - Find port **8000** → right-click → **Port Visibility** → set to **Public** (this lets the browser make a secure WebSocket connection).
   - Click the 🌐 globe icon to confirm you see `{"status": "LinguaBridge running"}`.

5. **Open the frontend**
   - In the Codespace terminal, open a **second terminal** (click the `+` icon).
   - Run:

     ```bash
     cd frontend
     python3 -m http.server 3000
     ```

   - Back in the **Ports** tab, forward port **3000** and open it in the browser.
   - The LinguaBridge UI will appear.

6. **Test microphone & streaming**
   - Click **Enable Microphone** — the browser will ask for permission. Click *Allow*.
   - The status indicator should change to **Mic: granted ✓** and the **Start Streaming** button becomes clickable.
   - Click **Start Streaming**.
     - The **WS** badge should turn green: **WS: connected ✓**
     - The **Streaming** badge should say **Streaming: on 🔴**
     - The counters (**Chunks sent**, **Bytes sent**, **Backend bytes received**) should increment every ~250 ms.
   - Switch to the terminal running the backend and watch bytes/sec log lines appear.
   - Click **Stop Streaming** to end the session.

---

### Option B — Run locally on your own computer

> You need Python 3.9+ installed. Check with `python --version`.

1. **Clone the repo** (if you haven't already):

   ```bash
   git clone https://github.com/florianmgedeon/linguabridge.git
   cd linguabridge
   ```

2. **Install dependencies**:

   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Start the backend**:

   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

4. **Open the frontend** — in a new terminal window:

   ```bash
   cd frontend
   python3 -m http.server 3000
   ```

5. **Open your browser** and go to `http://localhost:3000`

6. **Test** the same way as step 6 above (mic permission → Start Streaming → watch counters).

---

## API Endpoints

| Method    | Path        | Description |
|-----------|-------------|-------------|
| GET       | `/`         | Health-check: `{"status": "LinguaBridge running"}` |
| WebSocket | `/ws/audio` | Receives binary audio chunks; replies with `{"type":"ack","chunks_received":N,"bytes_received":N}` |

---

## What's Coming Next

- Speech-to-text (transcription) — PR 3
- Direction switching (DE→EN or EN→DE)
- Translation via AI API
- Text-to-speech output
- Ear routing (left/right channel per speaker)

---

*LinguaBridge ist eine lokal gehostete Webanwendung (GitHub Codespace + Zugriff über localhost im Browser), die ausschließlich Deutsch ↔ Englisch in nahezu Echtzeit übersetzt.*