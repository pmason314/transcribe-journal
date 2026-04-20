# Transcribe Journal

A two-component system for automatically transcribing audio journal entries and saving them as Markdown notes.

## Architecture

```
[Watcher Machine]                          [Server Machine]
  Audio file dropped                         Granite Speech 3.3-2B model
  into watched folder                        FastAPI transcription server
       │                                              │
       │  POST /transcribe (audio file)              │
       └─────────────────────────────────────────────┘
                                                      │
       ┌─────────────────────────────────────────────┘
       │  transcribed text
       ▼
  Ollama (text cleanup)
       │
       ▼
  Obsidian journal file (YYYY-MM-DD.md)
```

**Server** (`server/server.py`): Runs the IBM Granite Speech 3.3-2B model and exposes a REST API for audio transcription. Intended to be deployed on a machine with enough RAM (~5 GB) to run the model.

**Watcher** (`watcher/watcher.py`): Polls a local folder for new audio files, sends them to the server for transcription, runs the transcript through Ollama for cleanup, and appends the result to today's journal entry.

Both machines clone this repository with a standard `git clone`. Model files are not stored in git and must be downloaded separately on the server — see [DEPLOYMENT.md](DEPLOYMENT.md) for details.

## Watcher: What it does

Drop an audio file (mp3, wav, m4a, ogg, flac, aac, wma) into the configured watch folder and the watcher will:

1. Detect the new file via polling
2. Send it to the transcription server
3. Clean up the transcript with Ollama
4. Append the cleaned text to today's journal file (`YYYY-MM-DD.md`)
5. Move the audio to a `.processed/` subfolder
6. Clean up processed audio older than a configurable number of days

Journal files are saved as Markdown with YAML frontmatter, compatible with Obsidian and similar editors.

## Requirements

| Component | Requirements                                                                 |
| --------- | ---------------------------------------------------------------------------- |
| Server    | Python 3.13+, ~5 GB RAM, Granite Speech model files                          |
| Watcher   | Python 3.13+, [Ollama](https://ollama.com) running locally or on the network |

## Quick start

See [DEPLOYMENT.md](DEPLOYMENT.md) for full setup instructions for both machines.

## Supported Audio Formats

- MP3 (.mp3)
- WAV (.wav)
- M4A (.m4a)
- OGG (.ogg)
- FLAC (.flac)
- AAC (.aac)
- WMA (.wma)
