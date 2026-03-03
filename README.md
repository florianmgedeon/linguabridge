# LinguaBridge

LinguaBridge is a locally hosted web application (GitHub Codespaces + browser) that transcribes speech in **English** and **German** in near real-time using [Deepgram](https://deepgram.com/) streaming STT. Translation and TTS are coming in future PRs.

---

## Project Structure

```
linguabridge/
├── backend/
│   ├── main.py                    ← FastAPI server (HTTP + WebSocket)
│   ├── requirements.txt           ← Python dependencies
│   └── stt/
│       └── deepgram_streaming.py  ← Deepgram Streaming STT client
├── frontend/
│   ├── index.html                 ← Browser UI
│   └── app.js                     ← Microphone, device, and streaming logic
├── .env.example                   ← Template for environment variables
└── README.md
```

---

## How to Run & Test (Step-by-Step)

> **Both options below require a Deepgram API key.**
> Sign up at [console.deepgram.com](https://console.deepgram.com) — a free tier is available.

---

### Option A — GitHub Codespaces (recommended)

> Codespaces gives you a full Linux computer inside your browser. No local install needed.

#### Step 1 — Open a Codespace

- On the repository page on GitHub, click the green **Code** button.
- Choose the **Codespaces** tab → **Create codespace on main**.
- Wait ~1 minute for the environment to start.

#### Step 2 — Create your `.env` file with the Deepgram API key

In the Codespace terminal, run these two commands **exactly as shown** (replace `YOUR_KEY_HERE` with your real Deepgram key):

```bash
cp .env.example .env
```

Then open the `.env` file (click it in the file explorer on the left) and change:

```
DEEPGRAM_API_KEY=your_deepgram_api_key_here
```

to your real key, e.g.:

```
DEEPGRAM_API_KEY=abc123yourkeyhere
```

Save the file. **This file is in `.gitignore` — it will never be committed to GitHub.**

> 💡 **Why is this needed?** The backend sends your audio to Deepgram's servers for transcription. Deepgram requires an API key to verify who is making the request. We keep it in `.env` so it never accidentally ends up on GitHub.

#### Step 3 — Install Python dependencies

```bash
pip install -r backend/requirements.txt
```

#### Step 4 — Start the backend server

Make sure you are in the **project root** (the `linguabridge/` folder, not inside `backend/`). Run:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> ✅ The server has loaded your `.env` file automatically. If `DEEPGRAM_API_KEY` is missing, the browser will show a red error message when you start streaming.

#### Step 5 — Make port 8000 public

- Look at the **Ports** tab at the bottom of the Codespace (next to the Terminal).
- Find **port 8000** → right-click → **Port Visibility** → set to **Public**.
- Click the 🌐 globe icon next to port 8000. You should see `{"status": "LinguaBridge running"}` — that confirms the backend is up.

#### Step 6 — Open the frontend

Open a **second terminal** (click the `+` icon next to the Terminal tab). Then run:

```bash
cd frontend
python3 -m http.server 3000
```

> ⚠️ Make sure you run these commands in a **new terminal**, starting from the project root. If you get `bash: cd: frontend: No such file or directory`, you may already be inside the `frontend/` folder — just run `python3 -m http.server 3000` without the `cd` step.

Back in the **Ports** tab, find **port 3000**, make it **Public**, and open it in the browser. The LinguaBridge UI will appear.

#### Step 7 — Test live transcription

1. Click **Enable Microphone** — the browser will ask for permission. Click *Allow*.
2. The status indicator changes to **Mic: granted ✓** and the **Start Streaming** button becomes clickable.
3. Select your speaking language: **English** or **Deutsch (German)**.
4. Click **Start Streaming**.
   - The **WS** badge turns green: **WS: connected ✓**
   - The **Streaming** badge shows **Streaming: on 🔴**
5. Start talking — you will see words appear live in the **Live Transcript** box:
   - *Grey/italic* text = Deepgram's best guess while you're still speaking
   - **Black** text = finalised words (Deepgram is confident)
6. Click **Stop Streaming** when done.

---

### Option B — Run locally on your own computer

> You need Python 3.9+. Check with `python --version`.

1. **Clone the repo**:

   ```bash
   git clone https://github.com/florianmgedeon/linguabridge.git
   cd linguabridge
   ```

2. **Create your `.env` file**:

   ```bash
   cp .env.example .env
   ```

   Open `.env` and replace `your_deepgram_api_key_here` with your real Deepgram key.

3. **Install dependencies**:

   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Start the backend** (from the project root):

   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

5. **Open the frontend** — in a new terminal, from the project root:

   ```bash
   cd frontend
   python3 -m http.server 3000
   ```

6. Open `http://localhost:3000` in your browser and follow Step 7 above.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Red error in transcript box: *DEEPGRAM_API_KEY is not set* | Create `.env` from `.env.example` and add your key, then restart the backend |
| `bash: cd: frontend: No such file or directory` | You're already inside the `frontend/` folder — just run `python3 -m http.server 3000` |
| Transcript box stays empty after speaking | Check the backend terminal for error messages; confirm the key in `.env` is correct |
| WS error badge | The backend is not running, or port 8000 is not set to Public in Codespaces |
| Mic denied | Refresh the page and click *Allow* when the browser asks for microphone permission |

---

## API Endpoints

| Method    | Path        | Description |
|-----------|-------------|-------------|
| GET       | `/`         | Health-check: `{"status": "LinguaBridge running"}` |
| WebSocket | `/ws/audio?lang=en` | Receives binary audio; forwards to Deepgram; replies with `{"type":"transcript",...}` or `{"type":"error",...}` |

Supported `lang` values: `en` (English), `de` (German).

---

## What's Coming Next

- Translation (DE→EN or EN→DE) via AI API — PR 4
- Text-to-speech output — PR 5
- Ear routing (left/right channel per speaker)

---

*LinguaBridge ist eine lokal gehostete Webanwendung (GitHub Codespace + Browser), die Deutsch ↔ Englisch in nahezu Echtzeit transkribiert und übersetzt.*