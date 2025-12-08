#!/usr/bin/env python3
"""Audio file watcher and transcription service.

Watches a directory for new audio files, transcribes them using a local endpoint,
cleans up the text with Ollama, and saves the result.
"""

import logging
import time
from pathlib import Path

import httpx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Configuration
WATCH_FOLDER = Path("/mnt/syncthing/voice")
TRANSCRIBE_URL = "http://192.168.0.165:8000/transcribe"
OLLAMA_URL = "http://localhost:11434/api/generate"
OUTPUT_FOLDER = Path.home() / "transcribed_journals"
PROCESSED_FOLDER = WATCH_FOLDER / ".processed"

# Audio file extensions to watch for
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma"}

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
        "model": "llama3.2",  # Adjust model name as needed
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

    # Save the cleaned text
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_FOLDER / f"{audio_file.stem}.txt"

    output_file.write_text(cleaned_text, encoding="utf-8")
    logger.info("Saved cleaned transcription to: %s", output_file)

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


def main() -> None:
    """Run the audio file watcher service."""
    logger.info("Starting audio file watcher service")
    logger.info("Watching folder: %s", WATCH_FOLDER)
    logger.info("Output folder: %s", OUTPUT_FOLDER)

    # Ensure watch folder exists
    WATCH_FOLDER.mkdir(parents=True, exist_ok=True)

    # Create observer and event handler
    event_handler = AudioFileHandler()
    observer = Observer()
    observer.schedule(event_handler, str(WATCH_FOLDER), recursive=False)

    # Start watching
    observer.start()
    logger.info("Watcher started successfully")

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
