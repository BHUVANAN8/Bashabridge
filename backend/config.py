"""
BhashaBridge AI - Configuration Module
Centralized configuration for all Sarvam AI services and app settings.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SarvamConfig:
    """Configuration for Sarvam AI API services."""

    api_key: str = field(default_factory=lambda: os.getenv("SARVAM_API_KEY", ""))
    base_url: str = "https://api.sarvam.ai"

    # ── Model Identifiers ──────────────────────────────────────────────
    stt_model: str = "saaras:v3"         # Speech-to-Text (Saaras v3)
    tts_model: str = "bulbul:v3"         # Text-to-Speech (Bulbul v3)
    translate_model: str = "mayura:v1"   # Translation (Mayura v1)

    # ── STT Settings ───────────────────────────────────────────────────
    stt_language_code: str = "auto"      # Auto-detect source language
    stt_mode: str = "transcribe"         # transcribe | translate | codemix

    # ── TTS Settings ───────────────────────────────────────────────────
    tts_target_language: str = "hi-IN"
    tts_speaker: str = "meera"           # Default Bulbul speaker voice
    tts_pace: float = 1.0               # Speech speed multiplier
    tts_sample_rate: int = 16000         # Audio sample rate (Hz)

    # ── Translation Settings ───────────────────────────────────────────
    default_source_lang: str = "ta-IN"   # Tamil
    default_target_lang: str = "hi-IN"   # Hindi


@dataclass
class StreamingConfig:
    """Configuration for real-time audio streaming."""

    chunk_duration_ms: int = 500         # Process audio in 500ms chunks
    chunk_size_bytes: int = 16000        # ~500ms at 16kHz 16-bit mono
    max_buffer_size: int = 160000        # Max 5 seconds of buffered audio
    silence_threshold: float = 0.01      # RMS threshold for silence detection
    silence_timeout_ms: int = 1500       # End-of-utterance silence (ms)
    reconnect_delay_ms: int = 2000       # WebSocket reconnection delay
    max_reconnect_attempts: int = 5
    heartbeat_interval_s: int = 30       # WebSocket keepalive interval


@dataclass
class AppConfig:
    """Top-level application configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    cors_origins: list = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ])
    log_level: str = "info"

    sarvam: SarvamConfig = field(default_factory=SarvamConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)


# ── Supported Languages ─────────────────────────────────────────────────
SUPPORTED_LANGUAGES = {
    "hi-IN": {"name": "Hindi",      "native": "हिन्दी",    "code": "hi-IN"},
    "ta-IN": {"name": "Tamil",      "native": "தமிழ்",      "code": "ta-IN"},
    "te-IN": {"name": "Telugu",     "native": "తెలుగు",    "code": "te-IN"},
    "kn-IN": {"name": "Kannada",    "native": "ಕನ್ನಡ",     "code": "kn-IN"},
    "ml-IN": {"name": "Malayalam",  "native": "മലയാളം",   "code": "ml-IN"},
    "bn-IN": {"name": "Bengali",    "native": "বাংলা",     "code": "bn-IN"},
    "gu-IN": {"name": "Gujarati",   "native": "ગુજરાતી",   "code": "gu-IN"},
    "mr-IN": {"name": "Marathi",    "native": "मराठी",     "code": "mr-IN"},
    "pa-IN": {"name": "Punjabi",    "native": "ਪੰਜਾਬੀ",    "code": "pa-IN"},
    "or-IN": {"name": "Odia",       "native": "ଓଡ଼ିଆ",     "code": "or-IN"},
    "en-IN": {"name": "English",    "native": "English",   "code": "en-IN"},
}

# ── Language Code Aliases ────────────────────────────────────────────────
LANG_ALIASES = {
    "hindi": "hi-IN", "tamil": "ta-IN", "telugu": "te-IN",
    "kannada": "kn-IN", "malayalam": "ml-IN", "bengali": "bn-IN",
    "gujarati": "gu-IN", "marathi": "mr-IN", "punjabi": "pa-IN",
    "odia": "or-IN", "english": "en-IN",
}
