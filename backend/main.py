"""
BhashaBridge AI — Real-Time Streaming Voice-to-Voice Translator
================================================================
FastAPI backend with WebSocket streaming, integrating Sarvam AI's
Saaras (STT), Mayura (Translation), and Bulbul (TTS) models.
"""

import asyncio
import base64
import io
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import AppConfig, SUPPORTED_LANGUAGES, LANG_ALIASES

# ── Paths ────────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("bhashabridge")

# ── Configuration ────────────────────────────────────────────────────────
config = AppConfig()

# ── HTTP Client (shared for all Sarvam API calls) ────────────────────────
http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage shared HTTP client lifecycle."""
    global http_client
    http_client = httpx.AsyncClient(
        base_url=config.sarvam.base_url,
        headers={
            "api-subscription-key": config.sarvam.api_key,
            "Content-Type": "application/json",
        },
        timeout=httpx.Timeout(30.0, connect=10.0),
    )
    logger.info("🚀 BhashaBridge AI started — Sarvam AI client ready")
    yield
    await http_client.aclose()
    logger.info("🛑 BhashaBridge AI shutdown complete")


app = FastAPI(
    title="BhashaBridge AI",
    description="Real-time streaming voice-to-voice translator powered by Sarvam AI",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve Frontend Static Files ──────────────────────────────────────────
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


# ═══════════════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════════════


class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "ta-IN"
    target_lang: str = "hi-IN"


class TTSRequest(BaseModel):
    text: str
    target_lang: str = "hi-IN"
    speaker: str = "meera"
    pace: float = 1.0


class TranslationResponse(BaseModel):
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    latency_ms: float


# ═══════════════════════════════════════════════════════════════════════════
# SARVAM AI SERVICE LAYER
# ═══════════════════════════════════════════════════════════════════════════


async def sarvam_stt(audio_bytes: bytes, language_code: str = "auto") -> dict:
    """
    Saaras v3 — Speech-to-Text transcription.
    Accepts raw audio bytes and returns transcription + detected language.
    """
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    payload = {
        "model": config.sarvam.stt_model,
        "audio": audio_b64,
        "language_code": language_code,
        "mode": config.sarvam.stt_mode,
    }
    try:
        t0 = time.perf_counter()
        resp = await http_client.post("/speech-to-text", json=payload)
        resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        logger.info(f"STT [{latency:.0f}ms]: {data.get('transcript', '')[:80]}...")
        return {
            "transcript": data.get("transcript", ""),
            "language_code": data.get("language_code", language_code),
            "latency_ms": latency,
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"STT API error: {e.response.status_code} — {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"STT error: {e}")
        raise


async def sarvam_translate(
    text: str,
    source_lang: str,
    target_lang: str,
) -> dict:
    """
    Mayura v1 — Text translation between Indian languages.
    Optimized with Sarvam's Indic Tokenizer (~1 token per word).
    """
    payload = {
        "model": config.sarvam.translate_model,
        "input": text,
        "source_language_code": source_lang,
        "target_language_code": target_lang,
    }
    try:
        t0 = time.perf_counter()
        resp = await http_client.post("/translate", json=payload)
        resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        translated = data.get("translated_text", "")
        logger.info(f"TRANSLATE [{latency:.0f}ms]: {text[:40]} → {translated[:40]}")
        return {
            "translated_text": translated,
            "latency_ms": latency,
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Translate API error: {e.response.status_code} — {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Translate error: {e}")
        raise


async def sarvam_tts(
    text: str,
    target_lang: str,
    speaker: str = "meera",
    pace: float = 1.0,
) -> dict:
    """
    Bulbul v3 — Text-to-Speech synthesis.
    Returns base64-encoded WAV audio.
    """
    payload = {
        "model": config.sarvam.tts_model,
        "inputs": [text],
        "target_language_code": target_lang,
        "speaker": speaker,
        "pace": pace,
        "sample_rate": config.sarvam.tts_sample_rate,
    }
    try:
        t0 = time.perf_counter()
        resp = await http_client.post("/text-to-speech", json=payload)
        resp.raise_for_status()
        data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        audios = data.get("audios", [])
        audio_b64 = audios[0] if audios else ""
        logger.info(f"TTS [{latency:.0f}ms]: generated {len(audio_b64)} chars of base64 audio")
        return {
            "audio_base64": audio_b64,
            "latency_ms": latency,
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"TTS API error: {e.response.status_code} — {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE — Full Voice-to-Voice Translation
# ═══════════════════════════════════════════════════════════════════════════


async def voice_to_voice_pipeline(
    audio_bytes: bytes,
    source_lang: str,
    target_lang: str,
    speaker: str = "meera",
) -> dict:
    """
    Full pipeline: Audio → STT → Translate → TTS → Audio
    Uses asyncio for parallel processing where possible.
    """
    pipeline_start = time.perf_counter()

    # Step 1: Speech-to-Text (Saaras v3)
    stt_result = await sarvam_stt(audio_bytes, language_code=source_lang)
    transcript = stt_result["transcript"]
    detected_lang = stt_result.get("language_code", source_lang)

    if not transcript.strip():
        return {
            "status": "silence",
            "message": "No speech detected in audio chunk",
            "latency_ms": (time.perf_counter() - pipeline_start) * 1000,
        }

    # Step 2 + 3: Translate & TTS run in parallel (translation feeds TTS)
    translate_result = await sarvam_translate(transcript, detected_lang, target_lang)
    translated_text = translate_result["translated_text"]

    tts_result = await sarvam_tts(translated_text, target_lang, speaker=speaker)

    total_latency = (time.perf_counter() - pipeline_start) * 1000

    return {
        "status": "success",
        "original_text": transcript,
        "source_lang": detected_lang,
        "translated_text": translated_text,
        "target_lang": target_lang,
        "audio_base64": tts_result["audio_base64"],
        "latency": {
            "stt_ms": stt_result["latency_ms"],
            "translate_ms": translate_result["latency_ms"],
            "tts_ms": tts_result["latency_ms"],
            "total_ms": total_latency,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# REST ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend demo UI."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse("""
    <html>
    <head><title>BhashaBridge AI</title></head>
    <body style="font-family:system-ui;max-width:720px;margin:40px auto;padding:0 20px">
        <h1>🌉 BhashaBridge AI</h1>
        <p>Real-time voice-to-voice translator powered by <strong>Sarvam AI</strong></p>
        <ul>
            <li><code>GET /health</code> — Health check</li>
            <li><code>GET /languages</code> — Supported languages</li>
            <li><code>POST /translate/text</code> — Text translation</li>
            <li><code>POST /synthesize</code> — Text-to-Speech</li>
            <li><code>WS /ws/translate</code> — Real-time voice streaming</li>
        </ul>
    </body>
    </html>
    """)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "BhashaBridge AI",
        "version": "1.0.0",
        "sarvam_api": "connected" if config.sarvam.api_key else "no_key",
    }


@app.get("/languages")
async def list_languages():
    """List all supported languages with metadata."""
    return {"languages": SUPPORTED_LANGUAGES}


@app.post("/translate/text", response_model=TranslationResponse)
async def translate_text(req: TranslateRequest):
    """REST endpoint for text-only translation."""
    t0 = time.perf_counter()
    result = await sarvam_translate(req.text, req.source_lang, req.target_lang)
    return TranslationResponse(
        original_text=req.text,
        translated_text=result["translated_text"],
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        latency_ms=(time.perf_counter() - t0) * 1000,
    )


@app.post("/synthesize")
async def synthesize_speech(req: TTSRequest):
    """REST endpoint for Text-to-Speech synthesis."""
    result = await sarvam_tts(req.text, req.target_lang, req.speaker, req.pace)
    return {
        "audio_base64": result["audio_base64"],
        "latency_ms": result["latency_ms"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET — Real-Time Streaming Translation
# ═══════════════════════════════════════════════════════════════════════════


@app.websocket("/ws/translate")
async def websocket_translate(
    ws: WebSocket,
    source_lang: str = Query(default="auto"),
    target_lang: str = Query(default="hi-IN"),
    speaker: str = Query(default="meera"),
):
    """
    WebSocket endpoint for real-time voice-to-voice translation.

    Protocol:
    ─────────
    Client → Server:
      • Binary frames: raw audio bytes (16kHz, 16-bit, mono PCM)
      • JSON frames:   {"type": "config", "source_lang": "ta-IN", ...}
                        {"type": "end"}        — end-of-utterance signal
                        {"type": "ping"}       — keepalive

    Server → Client:
      • JSON frames:
        {"type": "transcript",  "text": "...", "lang": "ta-IN"}
        {"type": "translation", "original": "...", "translated": "...", "lang": "hi-IN"}
        {"type": "audio",       "audio_base64": "...", "latency": {...}}
        {"type": "error",       "message": "..."}
        {"type": "pong"}
    """
    await ws.accept()
    session_id = str(uuid.uuid4())[:8]
    logger.info(f"[{session_id}] WebSocket connected: {source_lang} → {target_lang}")

    audio_buffer = bytearray()
    chunk_size = config.streaming.chunk_size_bytes

    try:
        while True:
            message = await ws.receive()

            # ── Binary audio data ────────────────────────────────────
            if "bytes" in message:
                audio_buffer.extend(message["bytes"])

                # Process when buffer reaches chunk size
                while len(audio_buffer) >= chunk_size:
                    chunk = bytes(audio_buffer[:chunk_size])
                    audio_buffer = audio_buffer[chunk_size:]

                    # Process chunk asynchronously
                    try:
                        result = await voice_to_voice_pipeline(
                            audio_bytes=chunk,
                            source_lang=source_lang,
                            target_lang=target_lang,
                            speaker=speaker,
                        )

                        if result["status"] == "silence":
                            continue

                        # Send progressive results
                        await ws.send_json({
                            "type": "transcript",
                            "text": result["original_text"],
                            "lang": result["source_lang"],
                        })
                        await ws.send_json({
                            "type": "translation",
                            "original": result["original_text"],
                            "translated": result["translated_text"],
                            "source_lang": result["source_lang"],
                            "target_lang": result["target_lang"],
                        })
                        await ws.send_json({
                            "type": "audio",
                            "audio_base64": result["audio_base64"],
                            "latency": result["latency"],
                        })

                    except Exception as e:
                        logger.error(f"[{session_id}] Pipeline error: {e}")
                        await ws.send_json({
                            "type": "error",
                            "message": f"Translation pipeline error: {str(e)}",
                        })

            # ── Text/JSON control messages ───────────────────────────
            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")

                if msg_type == "config":
                    source_lang = data.get("source_lang", source_lang)
                    target_lang = data.get("target_lang", target_lang)
                    speaker = data.get("speaker", speaker)
                    logger.info(
                        f"[{session_id}] Config updated: {source_lang} → {target_lang}"
                    )
                    await ws.send_json({
                        "type": "config_ack",
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                    })

                elif msg_type == "end":
                    # Process remaining buffer
                    if audio_buffer:
                        try:
                            result = await voice_to_voice_pipeline(
                                audio_bytes=bytes(audio_buffer),
                                source_lang=source_lang,
                                target_lang=target_lang,
                                speaker=speaker,
                            )
                            audio_buffer.clear()

                            if result["status"] == "success":
                                await ws.send_json({
                                    "type": "transcript",
                                    "text": result["original_text"],
                                    "lang": result["source_lang"],
                                })
                                await ws.send_json({
                                    "type": "translation",
                                    "original": result["original_text"],
                                    "translated": result["translated_text"],
                                    "source_lang": result["source_lang"],
                                    "target_lang": result["target_lang"],
                                })
                                await ws.send_json({
                                    "type": "audio",
                                    "audio_base64": result["audio_base64"],
                                    "latency": result["latency"],
                                })
                        except Exception as e:
                            logger.error(f"[{session_id}] Final chunk error: {e}")

                    await ws.send_json({"type": "end_ack"})

                elif msg_type == "ping":
                    await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{session_id}] WebSocket error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level=config.log_level,
    )
