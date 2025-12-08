#!/usr/bin/env python3
"""Audio file watcher and transcription service.

Watches a directory for new audio files, transcribes them using a local endpoint,
cleans up the text with Ollama, and saves the result.
"""

import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Configuration from environment variables
WATCH_FOLDER = Path(os.getenv("WATCH_FOLDER", "/mnt/syncthing/Voice Recordings")).expanduser()
TRANSCRIBE_URL = os.getenv("TRANSCRIBE_URL", "http://192.168.0.165:8000/transcribe")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
JOURNAL_FOLDER = Path(os.getenv("JOURNAL_FOLDER", "/mnt/syncthing/Obsidian/Archive/Journal")).expanduser()
PROCESSED_FOLDER = WATCH_FOLDER / ".processed"

# Cleanup settings
AUDIO_FILE_MAX_AGE_DAYS = int(os.getenv("AUDIO_FILE_MAX_AGE_DAYS", "7"))

# Audio file extensions to watch for
AUDIO_EXTENSIONS_STR = os.getenv("AUDIO_EXTENSIONS", ".mp3,.wav,.m4a,.ogg,.flac,.aac,.wma")
AUDIO_EXTENSIONS = {ext.strip() for ext in AUDIO_EXTENSIONS_STR.split(",")}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class AudioFileHandler(FileSystemEventHandler):
    """Handle new audio file events."""

    def __init__(self) -> None:
        """Initialize the handler."""
        super().__init__()
        self.processing: set[str] = set()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events.

        Args:
            event: The file system event containing the file path.
        """
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if it's an audio file
        if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
            return

        # Avoid processing the same file multiple times
        if str(file_path) in self.processing:
            return

        logger.info("New audio file detected: %s", file_path)
        self.processing.add(str(file_path))

        try:
            process_audio_file(file_path)
        except Exception:
            logger.exception("Error processing file: %s", file_path)
        finally:
            self.processing.discard(str(file_path))


def transcribe_audio(audio_file: Path) -> str:
    """Transcribe audio file using the local endpoint.

    Args:
        audio_file: Path to the audio file to transcribe.

    Returns:
        The transcribed text.

    Raises:
        httpx.HTTPError: If the transcription request fails.
    """
    logger.info("Transcribing audio file: %s", audio_file)

    with audio_file.open("rb") as f:
        files = {"file": (audio_file.name, f, "audio/*")}

        with httpx.Client(timeout=300.0) as client:
            response = client.post(TRANSCRIBE_URL, files=files)
            response.raise_for_status()

            result = response.json()
            # Adjust this based on your API's response format
            transcription = result.get("text", result.get("transcription", ""))

            logger.info("Transcription complete: %d characters", len(transcription))
            return transcription


def clean_text_with_ollama(text: str) -> str:
    """Clean up transcribed text using Ollama.

    Args:
        text: The raw transcribed text to clean up.

    Returns:
        The cleaned up text.

    Raises:
        httpx.HTTPError: If the Ollama request fails.
    """
    logger.info("Cleaning text with Ollama")

    prompt = f"""Please clean up the following transcribed text. Fix any grammatical errors,
add proper punctuation, and make it more readable while preserving the original meaning and content.
Do not add any additional commentary - just return the cleaned up text.

Text to clean:
{text}"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(OLLAMA_URL, json=payload)
        response.raise_for_status()

        result = response.json()
        cleaned_text = result.get("response", "")

        logger.info("Text cleaning complete: %d characters", len(cleaned_text))
        return cleaned_text


def process_audio_file(audio_file: Path) -> None:
    """Process a single audio file through the full pipeline.

    Args:
        audio_file: Path to the audio file to process.
    """
    logger.info("Processing audio file: %s", audio_file)

    # Wait a bit to ensure the file is fully written
    time.sleep(2)

    # Transcribe the audio
    transcription = transcribe_audio(audio_file)

    if not transcription:
        logger.warning("Empty transcription for file: %s", audio_file)
        return

    # Clean up the text with Ollama
    cleaned_text = clean_text_with_ollama(transcription)

    # Save to journal file for today
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    journal_file = JOURNAL_FOLDER / f"{today}.md"

    JOURNAL_FOLDER.mkdir(parents=True, exist_ok=True)

    # Append to existing file or create new one
    if journal_file.exists():
        logger.info("Appending to existing journal file: %s", journal_file)
        with journal_file.open("a", encoding="utf-8") as f:
            f.write("\n\n---\n\n")
            f.write(cleaned_text)
            f.write("\n")
    else:
        logger.info("Creating new journal file: %s", journal_file)
        journal_file.write_text(cleaned_text, encoding="utf-8")

    logger.info("Saved cleaned transcription to: %s", journal_file)

    # Move the original audio file to processed folder
    PROCESSED_FOLDER.mkdir(parents=True, exist_ok=True)
    processed_file = PROCESSED_FOLDER / audio_file.name

    # Handle duplicate filenames
    counter = 1
    while processed_file.exists():
        processed_file = PROCESSED_FOLDER / f"{audio_file.stem}_{counter}{audio_file.suffix}"
        counter += 1

    audio_file.rename(processed_file)
    logger.info("Moved processed file to: %s", processed_file)


def cleanup_loop() -> None:
    """Run cleanup once daily on a background thread."""
    while True:
        try:
            cleanup_old_audio_files()
        except Exception:
            logger.exception("Error during cleanup")
        # Sleep for 24 hours before running cleanup again
        time.sleep(86400)  # 86400 seconds = 24 hours


def cleanup_old_audio_files() -> None:
    """Delete audio files older than AUDIO_FILE_MAX_AGE_DAYS."""
    cutoff_time = time.time() - (AUDIO_FILE_MAX_AGE_DAYS * 86400)  # 86400 seconds per day
    deleted_count = 0

    if not WATCH_FOLDER.exists():
        return

    for audio_file in WATCH_FOLDER.glob("*"):
        file_age_check = (
            audio_file.is_file()
            and audio_file.suffix.lower() in AUDIO_EXTENSIONS
            and audio_file.stat().st_mtime < cutoff_time
        )
        if file_age_check:
            try:
                audio_file.unlink()
                logger.info("Deleted old audio file: %s", audio_file)
                deleted_count += 1
            except OSError:
                logger.exception("Failed to delete file: %s", audio_file)

    if deleted_count > 0:
        logger.info("Cleaned up %d old audio files", deleted_count)


def process_existing_files(handler: AudioFileHandler) -> None:
    """Process any audio files that already exist in the watch folder.

    Args:
        handler: The AudioFileHandler instance with the processing set.
    """
    if not WATCH_FOLDER.exists():
        logger.warning("Watch folder does not exist: %s", WATCH_FOLDER)
        return

    audio_files = list(WATCH_FOLDER.glob("*"))
    logger.info("Scanning for existing audio files in %s", WATCH_FOLDER)
    logger.info("Found %d files total", len(audio_files))

    found_audio = False
    for file_path in audio_files:
        if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
            found_audio = True
            logger.info("Found existing audio file: %s", file_path)
            if str(file_path) not in handler.processing:
                handler.processing.add(str(file_path))
                try:
                    process_audio_file(file_path)
                except Exception:
                    logger.exception("Error processing existing file: %s", file_path)
                finally:
                    handler.processing.discard(str(file_path))

    if not found_audio:
        logger.info("No audio files found in watch folder")


def main() -> None:
    """Run the audio file watcher service."""
    logger.info("Starting audio file watcher service")
    logger.info("Watching folder: %s", WATCH_FOLDER)
    logger.info("Journal folder: %s", JOURNAL_FOLDER)
    logger.info("Max audio file age: %d days", AUDIO_FILE_MAX_AGE_DAYS)
    logger.info("Supported audio extensions: %s", ", ".join(sorted(AUDIO_EXTENSIONS)))

    # Ensure watch folder exists
    WATCH_FOLDER.mkdir(parents=True, exist_ok=True)

    # Start cleanup thread (runs once daily in background)
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    logger.info("Cleanup thread started (runs daily)")

    # Create observer and event handler for file watching
    event_handler = AudioFileHandler()
    observer = Observer()
    observer.schedule(event_handler, str(WATCH_FOLDER), recursive=False)

    # Start watching
    observer.start()
    logger.info("Watcher started successfully")

    # Process any existing files
    process_existing_files(event_handler)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
        observer.stop()

    observer.join()
    logger.info("Watcher stopped")


if __name__ == "__main__":
    main()
