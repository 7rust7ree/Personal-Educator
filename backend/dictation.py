"""Local voice input with live text.

While you talk, Vosk (a small, fast streaming recognizer) produces words in real time.
When you stop, Whisper re-transcribes the whole clip in the background for clean, punctuated text.
Both run on this machine: free and offline after the one-time model downloads.
"""
import io
import json
import logging
import queue
import threading
import urllib.request
import zipfile

import numpy as np

from . import config

log = logging.getLogger("educator.dictation")

SAMPLE_RATE = 16_000
WHISPER_MODEL = "base.en"
VOSK_NAME = "vosk-model-small-en-us-0.15"
VOSK_URL = f"https://alphacephei.com/vosk/models/{VOSK_NAME}.zip"
# Nudges Whisper toward CS vocabulary and spellings.
VOCAB_HINT = ("Thinking out loud about computer science: arrays, linked lists, pointers, Big-O, O(n log n), "
              "recursion, stack frames, binary search tree, hash table, heap, vector, C++, Python.")
KEEP_TAKES = 5  # recent recordings kept in memory for polishing


class Dictation:
    def __init__(self):
        self._lock = threading.Lock()
        self._stream = None
        self._frames: list[np.ndarray] = []
        self._level = 0.0
        self._queue: queue.Queue | None = None
        self._worker: threading.Thread | None = None
        self._final_parts: list[str] = []
        self._partial = ""
        self._takes: dict[int, np.ndarray] = {}
        self._take_no = 0
        self._whisper = None
        self._vosk = None
        self._model_lock = threading.Lock()
        self._whisper_lock = threading.Lock()

    # ---- models ----
    def vosk_model(self):
        with self._model_lock:
            if self._vosk is None:
                from vosk import Model, SetLogLevel
                SetLogLevel(-1)
                path = config.DATA_DIR / "models" / VOSK_NAME
                if not path.exists():
                    log.info("downloading %s", VOSK_URL)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    data = urllib.request.urlopen(VOSK_URL, timeout=120).read()
                    zipfile.ZipFile(io.BytesIO(data)).extractall(path.parent)
                self._vosk = Model(str(path))
            return self._vosk

    def whisper_model(self):
        with self._model_lock:
            if self._whisper is None:
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            return self._whisper

    def prewarm(self) -> None:
        """Load the small live model early. Whisper loads on first use to save memory."""
        def go():
            try:
                self.vosk_model()
            except Exception:
                log.exception("Vosk prewarm failed")
        threading.Thread(target=go, daemon=True).start()

    # ---- live recognition ----
    def _recognize(self, q: queue.Queue):
        import time
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(self.vosk_model(), SAMPLE_RATE)
        last_partial = 0.0
        while True:
            chunk = q.get()
            if chunk is None:
                text = json.loads(rec.FinalResult()).get("text", "")
                if text:
                    self._final_parts.append(text)
                self._partial = ""
                return
            if rec.AcceptWaveform(chunk):
                text = json.loads(rec.Result()).get("text", "")
                if text:
                    self._final_parts.append(text)
                self._partial = ""
            elif time.monotonic() - last_partial > 0.3 and q.qsize() < 3:
                # partial decoding is the expensive part: do it at most ~3x/s and never while behind
                self._partial = json.loads(rec.PartialResult()).get("partial", "")
                last_partial = time.monotonic()

    @property
    def recording(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        return self._level

    @property
    def live_text(self) -> str:
        return " ".join(p for p in [*self._final_parts, self._partial] if p)

    def _callback(self, indata, frames, time_info, status):
        mono = indata[:, 0].copy()
        with self._lock:
            self._frames.append(mono)
        if self._queue is not None:
            self._queue.put((np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes())
        rms = float(np.sqrt(np.mean(mono ** 2))) if len(mono) else 0.0
        self._level = min(1.0, rms * 12)

    def start(self) -> None:
        import sounddevice as sd
        if self._stream is not None:
            return
        self.vosk_model()  # make sure it's loaded before audio starts flowing
        with self._lock:
            self._frames = []
        self._final_parts, self._partial = [], ""
        self._queue = queue.Queue()
        self._worker = threading.Thread(target=self._recognize, args=(self._queue,), daemon=True)
        self._worker.start()
        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                      blocksize=SAMPLE_RATE // 4, callback=self._callback)
        self._stream.start()

    def _stop_stream(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        self._level = 0.0
        if self._queue is not None:
            self._queue.put(None)
            if self._worker:
                self._worker.join(timeout=60)  # let it finish the last words
            self._queue, self._worker = None, None
        with self._lock:
            audio = np.concatenate(self._frames) if self._frames else np.zeros(0, dtype=np.float32)
            self._frames = []
        return audio

    def cancel(self) -> None:
        self._stop_stream()

    def stop(self) -> dict:
        """Stop recording. Returns the live text right away plus a take number to polish later."""
        audio = self._stop_stream()
        self._take_no += 1
        if len(audio) >= SAMPLE_RATE * 0.3:
            self._takes[self._take_no] = audio
            for old in sorted(self._takes)[:-KEEP_TAKES]:
                del self._takes[old]
        return {"text": self.live_text, "take": self._take_no if self._take_no in self._takes else None}

    def polish(self, take: int) -> str:
        """Whisper transcription of a finished take: punctuated and more accurate."""
        audio = self._takes.pop(take, None)
        if audio is None:
            return ""
        with self._whisper_lock:
            segments, _ = self.whisper_model().transcribe(audio, language="en", vad_filter=True,
                                                          initial_prompt=VOCAB_HINT, beam_size=1)
            return " ".join(seg.text.strip() for seg in segments).strip()


dictation = Dictation()
