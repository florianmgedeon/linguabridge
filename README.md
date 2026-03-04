# LinguaBridge

LinguaBridge is a locally hosted web application (GitHub Codespaces + browser) that transcribes speech in **English** and **German** in near real-time using [Deepgram](https://deepgram.com/) streaming STT and translates automatically using [MyMemory](https://mymemory.translated.net/) (free, no API key required).

---

## Project Structure

```
linguabridge/
├── backend/
│   ├── main.py                    ← FastAPI server (HTTP + WebSocket)
│   ├── requirements.txt           ← Python dependencies
│   ├── stt/
│   │   └── deepgram_streaming.py  ← Deepgram Streaming STT client
│   └── translation/
│       └── openai_translate.py    ← MyMemory translation (EN ↔ DE)
├── frontend/
│   ├── index.html                 ← Browser UI
│   └── app.js                     ← Microphone, device, streaming, and translation logic
├── .env.example                   ← Template for environment variables
└── README.md
```

---

## How to Run & Test (Step-by-Step)

> **Both options below require a Deepgram API key.**
> Sign up at [console.deepgram.com](https://console.deepgram.com) — a free tier is available.
> Translation uses [MyMemory](https://mymemory.translated.net) which is **free and requires no account or API key**.

---

### Option A — GitHub Codespaces (recommended)

> Codespaces gives you a full Linux computer inside your browser. No local install needed.

#### Step 1 — Open a Codespace

- On the repository page on GitHub, click the green **Code** button.
- Choose the **Codespaces** tab → **Create codespace on main**.
- Wait ~1 minute for the environment to start.

#### Step 2 — Create your `.env` file with API keys

In the Codespace terminal, run these two commands **exactly as shown** (replace the placeholder values with your real keys):

```bash
cp .env.example .env
```

Then open the `.env` file (click it in the file explorer on the left) and fill in your Deepgram key:

```
DEEPGRAM_API_KEY=abc123yourkeyhere
```

Save the file. **This file is in `.gitignore` — it will never be committed to GitHub.**

> 💡 **No API key needed for translation!** Translation is handled by MyMemory — a free, public translation service. No account or credit card required.

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
3. Click **Start Streaming**.
   - The **WS** badge turns green: **WS: connected ✓**
   - The **Streaming** badge shows **Streaming: on 🔴**
4. Start talking — you will see words appear live in the **Live Transcript** box:
   - *Grey/italic* text = Deepgram's best guess while you're still speaking
   - **Black** text = finalised words (Deepgram is confident), prefixed with `[DE]` or `[EN]`
5. After each finalised sentence, the **Translation** panel below will show:
   - The original text labelled with its language, e.g. `[DE] Guten Morgen.`
   - The translated text labelled with the target language, e.g. `[EN] Good morning.`
6. The **"Detected language"** badge updates automatically each time a final transcript arrives.
7. Click **Stop Streaming** when done.

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

   Open `.env` and fill in your Deepgram key:

   ```
   DEEPGRAM_API_KEY=abc123yourkeyhere
   ```

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
| "Translation failed" in translation panel | The translation service may be temporarily unavailable — try again in a moment |
| "Translation rate limit reached" | The translation server throttled your requests — wait a few seconds and retry |
| Translation panel stays empty | Check the backend terminal for errors; the translation service requires an internet connection from your Codespace |
| Transcript box stays empty after speaking | Check the backend terminal for error messages; confirm the key in `.env` is correct |
| "Detected language" badge shows wrong language | Try a longer sentence (8+ characters); very short utterances fall back to the last confirmed language |
| `bash: cd: frontend: No such file or directory` | You're already inside the `frontend/` folder — just run `python3 -m http.server 3000` |
| WS error badge | The backend is not running, or port 8000 is not set to Public in Codespaces |
| Mic denied | Refresh the page and click *Allow* when the browser asks for microphone permission |

---

## PR6 — Automatic Language Detection

LinguaBridge now automatically detects whether the speaker is using **German** or **English**. There is no longer any need to manually select the language before you start speaking.

### How it works (plain English)

1. When you start streaming, the browser sends your microphone audio to the FastAPI backend.
2. The backend forwards the audio to Deepgram with **`detect_language=true`** enabled.  This tells Deepgram to figure out on its own which language is being spoken — you do not need to tell it.
3. Deepgram returns each finalised chunk of speech together with the language it detected (e.g. `"en"`, `"de-DE"`).
4. The backend normalises the code to `"en"` or `"de"` and applies a **stability policy** to avoid jittery direction changes on very short utterances (e.g. "OK", "ja"):
   - If the detected language is reliable **and** the transcript is at least 8 characters or 2 words → the new language is confirmed.
   - Otherwise → the last confirmed language is kept.
5. The translation direction is set automatically:
   - German detected → translate to English
   - English detected → translate to German
6. The UI shows a **"Detected language: DE / EN"** badge that updates after each final transcript, and each transcript line is prefixed with `[DE]` or `[EN]`.

### How to test

1. Start the backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
2. Open the frontend at `http://localhost:3000` (or your Codespace URL).
3. Click **Enable Microphone** → grant permission.
4. Click **Start Streaming**.
5. Speak a German sentence (e.g. *"Guten Morgen, wie geht es Ihnen?"*).
   - The transcript appears prefixed with `[DE]`.
   - The "Detected language" badge shows **DE**.
   - An English translation appears in the Translation panel.
6. Speak an English sentence (e.g. *"Good morning, how are you?"*).
   - The transcript appears prefixed with `[EN]`.
   - The "Detected language" badge shows **EN**.
   - A German translation appears in the Translation panel.
7. Observe the detected language indicator change dynamically as you switch languages.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| Translation direction is wrong | Check the backend terminal — look for lines like `Deepgram detected language: 'en'`. If detection looks incorrect, try speaking more clearly or using a longer sentence. |
| Detected language badge always shows "—" | Make sure the backend is running with the latest code; the feature requires `detect_language=true` in the Deepgram URL. |
| Translation panel stays empty | Ensure the backend has internet access and the Deepgram/OpenAI keys are set correctly. |

---



This section explains how the automatic translation feature works.

### How it works (plain English)

After you speak a sentence:
1. Deepgram transcribes your speech and marks it as **final** (the speaker has finished a chunk).
2. The backend detects your speaking language (`en` = English, `de` = German) from the language you selected.
3. It calls [MyMemory](https://mymemory.translated.net/) — a free, public translation API — to translate the sentence into the other language.
4. The translation is sent back to your browser and displayed in the **Translation** panel beneath the transcript.

Translation happens **in the background** — the live transcript keeps updating while you wait for the translation to come back. The WebSocket never freezes.

### Setup

No API key needed! Just make sure your Deepgram key is set and the backend is running.

#### Restart the backend

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Test Steps

1. **Enable microphone** and click **Start Streaming**.
2. **Speak German** (select "Deutsch" in the language dropdown) → you should see the English translation appear in the Translation panel below the transcript.
3. **Speak English** (select "English" in the language dropdown) → you should see the German translation.
4. Confirm:
   - Interim transcript updates live while you speak (grey/italic text)
   - Final transcript appears in black after you pause
   - Translation appears in blue beneath the original, labelled `[EN]` or `[DE]`

### Troubleshooting

| Problem | Solution |
|---------|----------|
| No translation appears | Check the backend terminal for errors; confirm the Codespace has internet access |
| "Translation rate limit reached" | MyMemory is temporarily throttling requests — wait a few seconds and try again |
| "Translation timed out" | MyMemory server is slow — try again in a moment |
| Wrong translation direction | Check the "Speaking language" selector matches what you are actually speaking |
| Console shows "Unknown language" | Only `en` and `de` are supported; other languages are ignored |

---

## API Endpoints

| Method    | Path        | Description |
|-----------|-------------|-------------|
| GET       | `/`         | Health-check: `{"status": "LinguaBridge running"}` |
| WebSocket | `/ws/audio` | Receives binary audio; forwards to Deepgram with automatic language detection; replies with `{"type":"transcript",...}` or `{"type":"error",...}` |

Language is detected automatically — no query parameters are required.

---

## What's Coming Next

- Text-to-speech output — PR 5
- Ear routing (left/right channel per speaker)

---

*LinguaBridge ist eine lokal gehostete Webanwendung (GitHub Codespace + Browser), die Deutsch ↔ Englisch in nahezu Echtzeit transkribiert und übersetzt.*