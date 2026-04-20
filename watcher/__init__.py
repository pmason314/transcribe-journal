"""Audio file watcher.

Polls a local folder for new audio files, sends them to the server for transcription, runs the transcript through
 Ollama for cleanup, and appends the result to today's journal entry.
"""
