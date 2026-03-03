# LinguaBridge

LinguaBridge is a locally hosted web application (GitHub Codespaces + browser access via forwarded localhost URL) that translates between **German ↔ English** in near real-time.

This PR (PR 1) sets up the full-stack scaffold and implements microphone permission + audio output device selection in the browser. No AI logic yet.

---

## Project Structure

```
linguabridge/
├── backend/
│   ├── main.py           ← FastAPI server
│   └── requirements.txt  ← Python dependencies
├── frontend/
│   ├── index.html        ← Browser UI
│   └── app.js            ← Microphone & device logic
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
   - Find port **8000** and click the 🌐 globe icon to open it in your browser.
   - You should see: `{"status": "LinguaBridge running"}`

5. **Open the frontend**
   - In the Codespace terminal, open a **second terminal** (click the `+` icon).
   - Run:

     ```bash
     cd frontend
     python3 -m http.server 3000
     ```

   - Back in the **Ports** tab, forward port **3000** and open it in the browser.
   - The LinguaBridge UI will appear.

6. **Test microphone & device selection**
   - Click **Enable Microphone** — the browser will ask for permission. Click *Allow*.
   - The status indicator should change to **Mic: granted ✓**
   - The input/output device dropdowns will populate with your real device names.
   - If you are using Chrome or Edge, changing the output device dropdown will switch where audio plays.

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

6. **Test** the same way as in step 6 above.

---

## API Endpoints (PR 1)

| Method | Path | Response |
|--------|------|----------|
| GET    | `/`  | `{"status": "LinguaBridge running"}` |

---

## What's Coming Next

- Speech-to-text (transcription)
- Direction switching (DE→EN or EN→DE)
- Translation via AI API
- Text-to-speech output
- Ear routing (left/right channel per speaker)

---

*LinguaBridge ist eine lokal gehostete Webanwendung (GitHub Codespace + Zugriff über localhost im Browser), die ausschließlich Deutsch ↔ Englisch in nahezu Echtzeit übersetzt.*