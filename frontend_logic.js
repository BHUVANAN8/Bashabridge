/**
 * ═══════════════════════════════════════════════════════════════════════════
 * BhashaBridge AI — Frontend Audio Streaming Client
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Handles:
 *   • Microphone capture via Web Audio API (16kHz, mono, 16-bit PCM)
 *   • WebSocket streaming to BhashaBridge backend
 *   • Real-time playback of translated audio
 *   • Reconnection with exponential backoff
 *   • Conversation Mode UI state management
 */

// ── Configuration ──────────────────────────────────────────────────────────

const CONFIG = {
    WS_URL: "ws://localhost:8000/ws/translate",
    API_URL: "http://localhost:8000",
    SAMPLE_RATE: 16000,
    CHUNK_DURATION_MS: 500,
    RECONNECT_DELAY_MS: 2000,
    MAX_RECONNECT_ATTEMPTS: 5,
    HEARTBEAT_INTERVAL_MS: 30000,
};

// ── Supported Languages ────────────────────────────────────────────────────

const LANGUAGES = {
    "hi-IN": { name: "Hindi", native: "हिन्दी", flag: "🇮🇳" },
    "ta-IN": { name: "Tamil", native: "தமிழ்", flag: "🇮🇳" },
    "te-IN": { name: "Telugu", native: "తెలుగు", flag: "🇮🇳" },
    "kn-IN": { name: "Kannada", native: "ಕನ್ನಡ", flag: "🇮🇳" },
    "ml-IN": { name: "Malayalam", native: "മലയാളം", flag: "🇮🇳" },
    "bn-IN": { name: "Bengali", native: "বাংলা", flag: "🇮🇳" },
    "gu-IN": { name: "Gujarati", native: "ગુજરાતી", flag: "🇮🇳" },
    "mr-IN": { name: "Marathi", native: "मराठी", flag: "🇮🇳" },
    "pa-IN": { name: "Punjabi", native: "ਪੰਜਾਬੀ", flag: "🇮🇳" },
    "or-IN": { name: "Odia", native: "ଓଡ଼ିଆ", flag: "🇮🇳" },
    "en-IN": { name: "English", native: "English", flag: "🇬🇧" },
};

// ═══════════════════════════════════════════════════════════════════════════
// BhashaBridgeClient — Core Streaming Client
// ═══════════════════════════════════════════════════════════════════════════

class BhashaBridgeClient {
    constructor(options = {}) {
        this.ws = null;
        this.audioContext = null;
        this.mediaStream = null;
        this.processor = null;
        this.isRecording = false;
        this.reconnectAttempts = 0;
        this.heartbeatTimer = null;

        // Language settings
        this.sourceLang = options.sourceLang || "auto";
        this.targetLang = options.targetLang || "hi-IN";
        this.speaker = options.speaker || "meera";

        // Callbacks
        this.onTranscript = options.onTranscript || (() => { });
        this.onTranslation = options.onTranslation || (() => { });
        this.onAudio = options.onAudio || (() => { });
        this.onError = options.onError || (() => { });
        this.onStatusChange = options.onStatusChange || (() => { });
        this.onLatency = options.onLatency || (() => { });
    }

    // ── WebSocket Connection ──────────────────────────────────────────────

    connect() {
        const params = new URLSearchParams({
            source_lang: this.sourceLang,
            target_lang: this.targetLang,
            speaker: this.speaker,
        });

        const url = `${CONFIG.WS_URL}?${params}`;
        this.ws = new WebSocket(url);
        this.ws.binaryType = "arraybuffer";

        this.ws.onopen = () => {
            console.log("🟢 WebSocket connected");
            this.reconnectAttempts = 0;
            this.onStatusChange("connected");
            this._startHeartbeat();
        };

        this.ws.onmessage = (event) => {
            this._handleMessage(event.data);
        };

        this.ws.onclose = (event) => {
            console.log(`🔴 WebSocket closed: ${event.code}`);
            this.onStatusChange("disconnected");
            this._stopHeartbeat();
            this._attemptReconnect();
        };

        this.ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            this.onError("Connection error. Retrying...");
        };
    }

    _handleMessage(data) {
        try {
            const msg = JSON.parse(data);

            switch (msg.type) {
                case "transcript":
                    this.onTranscript({
                        text: msg.text,
                        lang: msg.lang,
                        langName: LANGUAGES[msg.lang]?.name || msg.lang,
                    });
                    break;

                case "translation":
                    this.onTranslation({
                        original: msg.original,
                        translated: msg.translated,
                        sourceLang: msg.source_lang,
                        targetLang: msg.target_lang,
                        targetLangName:
                            LANGUAGES[msg.target_lang]?.name || msg.target_lang,
                    });
                    break;

                case "audio":
                    this._playAudio(msg.audio_base64);
                    if (msg.latency) {
                        this.onLatency(msg.latency);
                    }
                    break;

                case "error":
                    this.onError(msg.message);
                    break;

                case "pong":
                    // Heartbeat acknowledged
                    break;

                case "config_ack":
                    console.log(`Config updated: ${msg.source_lang} → ${msg.target_lang}`);
                    break;

                case "end_ack":
                    console.log("End-of-utterance acknowledged");
                    break;
            }
        } catch (e) {
            console.error("Failed to parse message:", e);
        }
    }

    _attemptReconnect() {
        if (this.reconnectAttempts >= CONFIG.MAX_RECONNECT_ATTEMPTS) {
            this.onError("Max reconnection attempts reached. Please refresh.");
            return;
        }

        const delay =
            CONFIG.RECONNECT_DELAY_MS * Math.pow(2, this.reconnectAttempts);
        this.reconnectAttempts++;
        this.onStatusChange("reconnecting");

        console.log(
            `Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`
        );
        setTimeout(() => this.connect(), delay);
    }

    _startHeartbeat() {
        this.heartbeatTimer = setInterval(() => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: "ping" }));
            }
        }, CONFIG.HEARTBEAT_INTERVAL_MS);
    }

    _stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    // ── Language Configuration ────────────────────────────────────────────

    updateConfig(sourceLang, targetLang, speaker) {
        this.sourceLang = sourceLang || this.sourceLang;
        this.targetLang = targetLang || this.targetLang;
        this.speaker = speaker || this.speaker;

        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(
                JSON.stringify({
                    type: "config",
                    source_lang: this.sourceLang,
                    target_lang: this.targetLang,
                    speaker: this.speaker,
                })
            );
        }
    }

    // ── Microphone Capture ────────────────────────────────────────────────

    async startRecording() {
        try {
            // Request microphone permission
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: CONFIG.SAMPLE_RATE,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });

            this.audioContext = new (window.AudioContext ||
                window.webkitAudioContext)({
                    sampleRate: CONFIG.SAMPLE_RATE,
                });

            const source = this.audioContext.createMediaStreamSource(
                this.mediaStream
            );

            // ScriptProcessorNode for chunked audio capture
            const bufferSize = Math.ceil(
                (CONFIG.SAMPLE_RATE * CONFIG.CHUNK_DURATION_MS) / 1000
            );
            // Use nearest power of 2
            const processorSize = Math.pow(
                2,
                Math.ceil(Math.log2(bufferSize))
            );
            this.processor = this.audioContext.createScriptProcessor(
                processorSize,
                1,
                1
            );

            this.processor.onaudioprocess = (event) => {
                if (!this.isRecording) return;

                const inputData = event.inputBuffer.getChannelData(0);

                // Convert Float32 to Int16 PCM
                const pcmData = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                    const s = Math.max(-1, Math.min(1, inputData[i]));
                    pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
                }

                // Send binary audio data over WebSocket
                if (this.ws?.readyState === WebSocket.OPEN) {
                    this.ws.send(pcmData.buffer);
                }
            };

            source.connect(this.processor);
            this.processor.connect(this.audioContext.destination);

            this.isRecording = true;
            this.onStatusChange("recording");
            console.log("🎙️ Recording started");
        } catch (error) {
            console.error("Microphone error:", error);
            if (error.name === "NotAllowedError") {
                this.onError(
                    "Microphone permission denied. Please allow access and try again."
                );
            } else if (error.name === "NotFoundError") {
                this.onError("No microphone found. Please connect one and try again.");
            } else {
                this.onError(`Microphone error: ${error.message}`);
            }
        }
    }

    stopRecording() {
        this.isRecording = false;

        // Signal end-of-utterance to server
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: "end" }));
        }

        // Cleanup audio resources
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach((track) => track.stop());
            this.mediaStream = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        this.onStatusChange("stopped");
        console.log("🛑 Recording stopped");
    }

    // ── Audio Playback ────────────────────────────────────────────────────

    async _playAudio(base64Audio) {
        if (!base64Audio) return;

        try {
            const audioBytes = Uint8Array.from(atob(base64Audio), (c) =>
                c.charCodeAt(0)
            );
            const audioBlob = new Blob([audioBytes], { type: "audio/wav" });
            const audioUrl = URL.createObjectURL(audioBlob);

            const audio = new Audio(audioUrl);
            audio.onended = () => URL.revokeObjectURL(audioUrl);
            await audio.play();

            this.onAudio({ playing: true, duration: audio.duration });
        } catch (error) {
            console.error("Audio playback error:", error);
            this.onError("Failed to play translated audio");
        }
    }

    // ── Cleanup ───────────────────────────────────────────────────────────

    disconnect() {
        this.stopRecording();
        this._stopHeartbeat();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// UI Controller — Conversation Mode Interface
// ═══════════════════════════════════════════════════════════════════════════

class ConversationUI {
    constructor() {
        this.client = null;
        this.conversationHistory = [];
    }

    init() {
        this.client = new BhashaBridgeClient({
            sourceLang: "auto",
            targetLang: "hi-IN",
            speaker: "meera",

            onTranscript: (data) => this._addTranscript(data),
            onTranslation: (data) => this._addTranslation(data),
            onAudio: (data) => this._updateAudioStatus(data),
            onError: (msg) => this._showError(msg),
            onStatusChange: (status) => this._updateStatus(status),
            onLatency: (latency) => this._updateLatency(latency),
        });

        this.client.connect();
        this._bindUI();
    }

    _bindUI() {
        // Bind record button
        const recordBtn = document.getElementById("record-btn");
        if (recordBtn) {
            recordBtn.addEventListener("mousedown", () => this.client.startRecording());
            recordBtn.addEventListener("mouseup", () => this.client.stopRecording());
            recordBtn.addEventListener("touchstart", (e) => {
                e.preventDefault();
                this.client.startRecording();
            });
            recordBtn.addEventListener("touchend", (e) => {
                e.preventDefault();
                this.client.stopRecording();
            });
        }

        // Bind language selectors
        const sourceLangSelect = document.getElementById("source-lang");
        const targetLangSelect = document.getElementById("target-lang");

        if (sourceLangSelect) {
            sourceLangSelect.addEventListener("change", (e) =>
                this.client.updateConfig(e.target.value, null, null)
            );
        }
        if (targetLangSelect) {
            targetLangSelect.addEventListener("change", (e) =>
                this.client.updateConfig(null, e.target.value, null)
            );
        }

        // Bind swap languages button
        const swapBtn = document.getElementById("swap-langs");
        if (swapBtn) {
            swapBtn.addEventListener("click", () => {
                const src = sourceLangSelect?.value;
                const tgt = targetLangSelect?.value;
                if (sourceLangSelect) sourceLangSelect.value = tgt;
                if (targetLangSelect) targetLangSelect.value = src;
                this.client.updateConfig(tgt, src, null);
            });
        }
    }

    _addTranscript(data) {
        const container = document.getElementById("transcript-output");
        if (container) {
            const entry = document.createElement("div");
            entry.className = "transcript-entry";
            entry.innerHTML = `
        <span class="lang-badge">${data.langName}</span>
        <span class="text">${data.text}</span>
      `;
            container.appendChild(entry);
            container.scrollTop = container.scrollHeight;
        }
    }

    _addTranslation(data) {
        const container = document.getElementById("translation-output");
        if (container) {
            const entry = document.createElement("div");
            entry.className = "translation-entry";
            entry.innerHTML = `
        <div class="original">${data.original}</div>
        <div class="arrow">→</div>
        <div class="translated">${data.translated}</div>
        <span class="lang-badge">${data.targetLangName}</span>
      `;
            container.appendChild(entry);
            container.scrollTop = container.scrollHeight;
        }

        this.conversationHistory.push(data);
    }

    _updateAudioStatus(data) {
        const indicator = document.getElementById("audio-indicator");
        if (indicator) {
            indicator.classList.toggle("playing", data.playing);
        }
    }

    _showError(message) {
        const container = document.getElementById("error-output");
        if (container) {
            container.textContent = message;
            container.style.display = "block";
            setTimeout(() => {
                container.style.display = "none";
            }, 5000);
        }
        console.error("BhashaBridge Error:", message);
    }

    _updateStatus(status) {
        const indicator = document.getElementById("status-indicator");
        if (indicator) {
            indicator.className = `status-${status}`;
            indicator.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        }
    }

    _updateLatency(latency) {
        const display = document.getElementById("latency-display");
        if (display) {
            display.innerHTML = `
        STT: ${latency.stt_ms?.toFixed(0)}ms |
        Translate: ${latency.translate_ms?.toFixed(0)}ms |
        TTS: ${latency.tts_ms?.toFixed(0)}ms |
        <strong>Total: ${latency.total_ms?.toFixed(0)}ms</strong>
      `;
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Initialize on DOM Ready
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", () => {
    const ui = new ConversationUI();
    ui.init();
});

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
    module.exports = { BhashaBridgeClient, ConversationUI, LANGUAGES, CONFIG };
}
