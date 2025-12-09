# Transcribe Journal

A background service that watches for audio files, transcribes them, and cleans up the text using AI.

## Features

- **Automatic file watching**: Monitors `/mnt/syncthing/voice` for new audio files
- **Audio transcription**: Sends audio files to a local transcription endpoint
- **Text cleanup**: Uses Ollama to clean up and format the transcribed text
- **Automatic organization**: Saves cleaned text and moves processed audio files

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure the service

Create a `.env` file in the project directory (use `.env.example` as a template):

```bash
cp .env.example .env
```

Edit `.env` to configure these settings:
- `WATCH_FOLDER`: Directory to watch for audio files (default: `"/mnt/syncthing/Voice Recordings"`)
- `TRANSCRIBE_URL`: URL of your transcription endpoint (default: `http://192.168.0.165:8000/transcribe`)
- `OLLAMA_URL`: URL of your Ollama instance (default: `http://192.168.0.165:11434/api/generate`)
- `OLLAMA_MODEL`: Ollama model to use for text cleanup (default: `llama3.2:latest`)
- `JOURNAL_FOLDER`: Where to save journal entries (default: `"/mnt/syncthing/Obsidian/Archive/Journal"`)
- `AUDIO_FILE_MAX_AGE_DAYS`: Days to keep audio files before cleanup (default: `7`)
- `NOTE_TIMEZONE`: Timezone for daily notes (default: `America/Los_Angeles`)

### 3. Test the service

Run the watcher manually to ensure everything works:

```bash
uv run --env-file .env watcher.py
```

### 4. Install as a systemd service (runs in background)

```bash
# Copy the service file to systemd
sudo cp transcribe-journal.service /etc/systemd/system/

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable transcribe-journal

# Start the service now
sudo systemctl start transcribe-journal

# Check the service status
sudo systemctl status transcribe-journal
```

## Usage

Once the service is running, simply drop audio files (mp3, wav, m4a, ogg, flac, aac, wma) into your configured watch folder. The service will:

1. Detect the new file
2. Transcribe it using your local endpoint
3. Clean up the text with Ollama
4. Append the cleaned text to today's journal file (`YYYY-MM-DD.md`) in your Obsidian journal folder
5. Move the original audio to the `.processed/` subfolder in your watch folder
6. Automatically clean up audio files older than 7 days (configurable)

The journal entries are saved as Markdown files with frontmatter, making them compatible with Obsidian and other Markdown editors.

## Monitoring

View real-time logs:
```bash
sudo journalctl -u transcribe-journal -f
```

View recent logs:
```bash
sudo journalctl -u transcribe-journal -n 100
```

## Management

```bash
# Stop the service
sudo systemctl stop transcribe-journal

# Restart the service
sudo systemctl restart transcribe-journal

# Disable the service (won't start on boot)
sudo systemctl disable transcribe-journal
```

## Supported Audio Formats

- MP3 (.mp3)
- WAV (.wav)
- M4A (.m4a)
- OGG (.ogg)
- FLAC (.flac)
- AAC (.aac)
- WMA (.wma)
