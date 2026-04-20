"""Granite Speech Transcription API server.

This module runs a FastAPI application that loads a pretrained speech-to-text
model and exposes endpoints to transcribe uploaded audio files and report
health/status. It handles model loading on startup, audio preprocessing with
torchaudio, and returns transcription results as JSON.
"""

import logging
import os
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import torch
import torchaudio
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, AutoTokenizer

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
PORT = int(os.getenv("PORT", "8000"))
# Default to loopback for improved security; to bind publicly set HOST env explicitly (e.g. "0.0.0.0")
HOST = os.getenv("HOST", "127.0.0.1")
# Comma-separated list of allowed hostnames/IPs (used for documentation/operational checks)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
MODEL_PATH = os.getenv("MODEL_PATH", "models/granite-speech-3.3-2b")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load model on startup, cleanup on shutdown."""
    logger.info("Loading model...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")

    try:
        processor = AutoProcessor.from_pretrained(MODEL_PATH)
        tokenizer = processor.tokenizer
        model = AutoModelForSpeechSeq2Seq.from_pretrained(MODEL_PATH, device_map=device, torch_dtype=torch.bfloat16)
        logger.info("Model loaded successfully!")

        # Store in app state
        app.state.processor = processor
        app.state.tokenizer = tokenizer
        app.state.model = model
        app.state.device = device
    except Exception:
        logger.exception("Failed to load model")
        raise

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Granite Speech Transcription API",
    description="AI-powered speech transcription service",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# System prompt for the model
def get_system_prompt() -> str:
    """Return the system prompt provided to the model.

    The prompt includes a knowledge cutoff date, the current date, and a brief
    assistant identity statement used as the system message for the transcription model.

    Returns:
        str: The formatted system prompt string.
    """
    today = datetime.now(tz=UTC).strftime("%B %d, %Y")
    return (
        f"Knowledge Cutoff Date: April 2024.\n"
        f"Today's Date: {today}.\n"
        "You are Granite, developed by IBM. You are a helpful AI assistant"
    )


def transcribe_audio(
    audio_path: str,
    processor: AutoProcessor,
    tokenizer: AutoTokenizer,
    model: AutoModelForSpeechSeq2Seq,
    device: str,
) -> str:
    """Transcribe audio file to text."""
    logger.info(f"Processing audio file: {audio_path}")

    try:
        # Load audio
        wav, sr = torchaudio.load(audio_path, normalize=True)
        logger.debug(f"Loaded audio: shape={wav.shape}, sample_rate={sr}")

        # Convert to mono if stereo
        if wav.shape[0] > 1:
            wav = torch.mean(wav, dim=0, keepdim=True)
            logger.debug("Converted to mono")

        # Resample if necessary
        if sr != 16000:
            resampler = torchaudio.transforms.Resample(sr, 16000)
            wav = resampler(wav)
            logger.debug("Resampled to 16kHz")

        # Create text prompt
        user_prompt = "<|audio|>can you transcribe the speech into a written format?"
        chat = [
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]
        prompt = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)

        # Run the processor+model
        logger.info("Running transcription model...")
        model_inputs = processor(prompt, wav, device=device, return_tensors="pt").to(device)
        model_outputs = model.generate(**model_inputs, max_new_tokens=200, do_sample=False, num_beams=1)

        # Extract transcription
        num_input_tokens = model_inputs["input_ids"].shape[-1]
        new_tokens = torch.unsqueeze(model_outputs[0, num_input_tokens:], dim=0)
        output_text = tokenizer.batch_decode(new_tokens, add_special_tokens=False, skip_special_tokens=True)

        result = output_text[0]

    except Exception:
        logger.exception("Transcription error")
        raise
    else:
        logger.info(f"Transcription complete: {len(result)} characters")
        return result


@app.get("/")
async def root() -> dict:
    """Health check endpoint."""
    return {
        "status": "online",
        "model": MODEL_PATH,
        "device": str(app.state.device),
        "version": "1.0.0",
    }


@app.get("/health")
async def health() -> dict:
    """Detailed health check for monitoring."""
    return {
        "status": "healthy",
        "model_loaded": app.state.model is not None,
        "device": str(app.state.device),
        "torch_version": torch.__version__,
    }


@app.post("/transcribe")
async def transcribe(audio: Annotated[UploadFile, File()]) -> JSONResponse:
    """Transcribe an audio file.

    Accepts WAV, MP3, FLAC, M4A, and other common audio formats.
    Returns the transcription as JSON.
    """
    # Accept common audio file extensions
    allowed_extensions = {
        ".wav",
        ".mp3",
        ".flac",
        ".m4a",
        ".ogg",
        ".opus",
        ".aac",
        ".wma",
    }
    file_ext = Path(audio.filename or "").suffix.lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
        )

    # Check file size
    content = await audio.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024 * 1024):.0f}MB",
        )

    logger.info(f"Received file: {audio.filename} ({len(content)} bytes)")

    # Save uploaded file temporarily
    tmp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        # Transcribe
        transcription = transcribe_audio(
            tmp_file_path,
            app.state.processor,
            app.state.tokenizer,
            app.state.model,
            app.state.device,
        )

        logger.info(f"Successfully transcribed: {audio.filename}")
        return JSONResponse(
            content={
                "transcription": transcription,
                "filename": audio.filename,
                "file_size": len(content),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Transcription failed for {audio.filename}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e!s}") from e
    finally:
        # Clean up temp file
        if tmp_file_path and Path(tmp_file_path).exists():
            try:
                Path(tmp_file_path).unlink()
                logger.debug(f"Cleaned up temp file: {tmp_file_path}")
            except OSError as e:
                logger.warning(f"Failed to delete temp file {tmp_file_path}: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info", access_log=True)
