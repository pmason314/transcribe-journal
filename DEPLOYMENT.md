# Deployment Guide

Both machines clone this repository with a standard `git clone`. Model files are not stored in git — see the download step in the Server section below.

---

## Server Machine

The server loads the Granite Speech 4.1-2B model and exposes a transcription API on port 8000.

### 1. Clone the repository

```bash
git clone https://github.com/pmason314/transcribe-journal.git
cd transcribe-journal
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Download model files

Model files are not included in the repository. Download them from Hugging Face:

```bash
uv run hf download ibm-granite/granite-speech-4.1-2b --local-dir server/models/granite-speech-4.1-2b
```

This requires ~5 GB of free disk space. The download will populate `server/models/granite-speech-4.1-2b/` with the safetensors weights and config files needed to run the server.

### 4. Configure environment

Copy `.env.example` to `.env` in the repo root and fill in the server section values:

```bash
cp .env.example .env
nano .env
```

### 5. Test the server manually

```bash
uv run --env-file .env python server/server.py
```

Confirm it's running:
```bash
curl http://localhost:8000/health
```

### 6. Install as a systemd service

Edit `transcribe-server.service` to set the correct paths for your machine, then install it:

```bash
# Update WorkingDirectory and User/Group in the service file first
nano transcribe-server.service

# Install
sudo cp transcribe-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable transcribe-server
sudo systemctl start transcribe-server
sudo systemctl status transcribe-server
```

Key fields to verify in the service file:

| Field              | Description                    |
| ------------------ | ------------------------------ |
| `User` / `Group`   | User to run the service as     |
| `WorkingDirectory` | Absolute path to the repo root |

### Environment variables

All environment variables for both components live in the root `.env`. See `.env.example` for the full list with descriptions.

| Variable                  | Component | Description                                              |
| ------------------------- | --------- | -------------------------------------------------------- |
| `MODEL_PATH`              | Server    | Path to the Granite Speech model (relative to repo root) |
| `PORT`                    | Server    | Port the API listens on (default: `8000`)                |
| `HOST`                    | Server    | Bind address (`0.0.0.0` to accept external connections)  |
| `WATCH_FOLDER`            | Watcher   | Directory to poll for new audio files                    |
| `TRANSCRIBE_URL`          | Watcher   | URL of the transcription server                          |
| `OLLAMA_URL`              | Watcher   | URL of the Ollama API                                    |
| `OLLAMA_MODEL`            | Watcher   | Ollama model used for text cleanup                       |
| `JOURNAL_FOLDER`          | Watcher   | Directory where journal Markdown files are saved         |
| `AUDIO_FILE_MAX_AGE_DAYS` | Watcher   | Days to keep processed audio files before deletion       |
| `NOTE_TIMEZONE`           | Watcher   | Timezone used when naming daily journal files            |
| `POLL_INTERVAL`           | Watcher   | Seconds between folder scans (default: `5`)              |
| `AUDIO_EXTENSIONS`        | Watcher   | Comma-separated list of audio extensions to process      |

### Managing the server service

```bash
sudo systemctl restart transcribe-server
sudo systemctl stop transcribe-server
sudo systemctl status transcribe-server

# Logs
sudo journalctl -u transcribe-server -f
tail -f ~/transcribe-journal/server/logs/server.log
tail -f ~/transcribe-journal/server/logs/error.log
```

### Uninstalling the server service

```bash
sudo systemctl stop transcribe-server
sudo systemctl disable transcribe-server
sudo rm /etc/systemd/system/transcribe-server.service
sudo systemctl daemon-reload
```

### Firewall

Open port 8000 to allow the watcher machine to connect:

```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

---

## Watcher Machine

The watcher polls a local folder for audio files, sends them to the server, and saves transcripts to an Obsidian journal via Ollama.

### 1. Clone the repository

```bash
git clone https://github.com/pmason314/transcribe-journal.git
cd transcribe-journal
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in the watcher section values:

```bash
cp .env.example .env
nano .env
```

See the environment variables table in the Server section above for descriptions of all available settings.

### 4. Test the watcher manually

```bash
uv run --env-file .env watcher/watcher.py
```

Drop an audio file into your `WATCH_FOLDER` and watch the logs to verify the full pipeline works end to end.

### 5. Install as a systemd service

Edit `transcribe-watcher.service` to set the correct paths for your machine, then install it:

```bash
nano transcribe-watcher.service

sudo cp transcribe-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable transcribe-watcher
sudo systemctl start transcribe-watcher
sudo systemctl status transcribe-watcher
```

Key fields to verify in the service file:

| Field              | Description                    |
| ------------------ | ------------------------------ |
| `User` / `Group`   | User to run the service as     |
| `WorkingDirectory` | Absolute path to the repo root |

### Managing the watcher service

```bash
sudo systemctl restart transcribe-watcher
sudo systemctl stop transcribe-watcher
sudo systemctl status transcribe-watcher

# Logs
sudo journalctl -u transcribe-watcher -f
sudo journalctl -u transcribe-watcher -n 100
```

### Uninstalling the watcher service

```bash
sudo systemctl stop transcribe-watcher
sudo systemctl disable transcribe-watcher
sudo rm /etc/systemd/system/transcribe-watcher.service
sudo systemctl daemon-reload
```

---

## Troubleshooting

### Server won't start
1. Check logs: `sudo journalctl -u transcribe-server -n 50`
2. Verify model files exist in `server/models/granite-speech-4.1-2b/`
3. Ensure the virtual environment was created: `ls .venv/`
4. Check available memory — the model requires ~5 GB RAM

### Watcher can't reach the server
1. Confirm the server is running: `curl http://<server-ip>:8000/health`
2. Check the firewall on the server: `sudo ufw status`
3. Verify `TRANSCRIBE_URL` in your `.env` points to the correct IP and port

### Empty or missing transcriptions
1. Check the server logs for model errors
2. Verify the audio file format is in the supported extensions list
3. Test transcription directly: `curl -X POST "http://<server-ip>:8000/transcribe" -F "audio=@test.wav"`

### Ollama errors
1. Confirm Ollama is running: `curl http://localhost:11434/api/tags`
2. Verify `OLLAMA_MODEL` is pulled: `ollama list`
3. Pull it if missing: `ollama pull qwen3.6`
