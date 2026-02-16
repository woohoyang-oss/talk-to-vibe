#!/usr/bin/env python3
"""
VoiceKey - Lightweight Speech-to-Text for Vibe Coding
Hold Right Option key → Record → Release → Transcribe → Paste

Uses Groq Whisper API (free tier, whisper-large-v3-turbo)

Usage:
    python voicekey.py              # Run with default settings
    python voicekey.py --key cmd_r  # Use Right Cmd as PTT key
    python voicekey.py --setup      # Re-enter API key
"""

__version__ = "0.2.0"

import os
import sys
import json
import time
import wave
import threading
import tempfile
import subprocess
import argparse
from pathlib import Path

# ─── Dependencies ───────────────────────────────────────────────
try:
    import sounddevice as sd
    import numpy as np
    from pynput import keyboard
    from groq import Groq
except ImportError:
    print("❌ Missing dependencies. Run: bash setup.sh")
    sys.exit(1)

# ─── Config ─────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".voicekey"
CONFIG_FILE = CONFIG_DIR / "config.json"

SAMPLE_RATE = 16000       # 16kHz - optimal for Whisper
CHANNELS = 1              # Mono
DTYPE = "int16"           # 16-bit

# PTT key mapping
KEY_MAP = {
    "alt_r":   keyboard.Key.alt_r,
    "alt_l":   keyboard.Key.alt_l,
    "cmd_r":   keyboard.Key.cmd_r,
    "ctrl_r":  keyboard.Key.ctrl_r,
    "f18":     keyboard.KeyCode.from_vk(0x4F),
    "f19":     keyboard.KeyCode.from_vk(0x50),
    "f20":     keyboard.KeyCode.from_vk(0x5A),
}

DEFAULT_PTT_KEY = "alt_r"  # Right Option key


# ─── Config Management ─────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config):
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    CONFIG_FILE.chmod(0o600)  # Owner read/write only (contains API key)


def setup_api_key(force=False):
    config = load_config()
    if "groq_api_key" in config and not force:
        return config["groq_api_key"]

    # Migrate from old openai key config
    if "openai_api_key" in config and not force:
        print("   ⚠️  OpenAI key found but switching to Groq. Run --setup to set Groq key.")

    print("\n🔑 Groq API Key Setup")
    print("   Get your FREE key at: https://console.groq.com/keys")

    while True:
        try:
            api_key = input("   Enter Groq API key: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n   Cancelled.")
            sys.exit(0)

        if not api_key:
            print("   ⚠️  API key cannot be empty. Try again.")
            continue

        if not api_key.startswith("gsk_"):
            print("   ⚠️  Groq keys start with 'gsk_'. Are you sure? (y/n) ", end="")
            try:
                confirm = input().strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\n   Cancelled.")
                sys.exit(0)
            if confirm != "y":
                continue

        break

    config["groq_api_key"] = api_key
    save_config(config)
    print("   ✅ Saved to ~/.voicekey/config.json\n")
    return api_key


# ─── Audio Recorder ─────────────────────────────────────────────
def find_real_microphone():
    """Find a real hardware microphone, skipping virtual audio devices."""
    virtual_keywords = ["blackhole", "soundflower", "loopback", "virtual", "aggregate"]
    devices = sd.query_devices()

    # First pass: find a real hardware mic
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            name_lower = d["name"].lower()
            if not any(vk in name_lower for vk in virtual_keywords):
                return i, d["name"]

    # Fallback: use system default
    return None, "system default"


class AudioRecorder:
    def __init__(self):
        self.recording = False
        self.audio_frames = []
        self.stream = None
        self.start_time = 0
        self.device_id, self.device_name = find_real_microphone()

    def start(self):
        """Start recording from microphone."""
        self.audio_frames = []
        self.recording = True
        self.start_time = time.time()

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._audio_callback,
                blocksize=1024,
                device=self.device_id,
            )
            self.stream.start()
        except sd.PortAudioError as e:
            self.recording = False
            print(f"\n  ❌ Microphone error: {e}")
            print("     Check System Settings → Privacy → Microphone")
            return False
        return True

    def stop(self):
        """Stop recording and return audio data."""
        self.recording = False
        duration = time.time() - self.start_time

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if duration < 0.3:
            return None, 0  # Too short, ignore

        audio_data = np.concatenate(self.audio_frames) if self.audio_frames else None
        return audio_data, duration

    def _audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            self.audio_frames.append(indata.copy())


# ─── Groq Whisper STT ──────────────────────────────────────────
class WhisperSTT:
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)

    def transcribe(self, audio_data):
        """Send audio to Groq Whisper API and return text."""
        # Save to temp WAV file
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_data.tobytes())

            # Call Groq Whisper API
            with open(tmp.name, "rb") as audio_file:
                result = self.client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=audio_file,
                )
            return result.text.strip()
        finally:
            os.unlink(tmp.name)


# ─── Text Output ────────────────────────────────────────────────
def paste_text(text):
    """Copy text to clipboard and simulate Cmd+V paste via pynput."""
    # Copy to clipboard using pbcopy (macOS)
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))

    # Small delay to ensure clipboard is ready
    time.sleep(0.1)

    # Simulate Cmd+V using pynput (works reliably across all macOS apps)
    from pynput.keyboard import Controller, Key
    kb = Controller()
    kb.press(Key.cmd)
    kb.press('v')
    kb.release('v')
    kb.release(Key.cmd)


# ─── Main App ───────────────────────────────────────────────────
class VoiceKey:
    def __init__(self, api_key, ptt_key_name=DEFAULT_PTT_KEY):
        self.recorder = AudioRecorder()
        self.stt = WhisperSTT(api_key)
        self.ptt_key = KEY_MAP.get(ptt_key_name, KEY_MAP[DEFAULT_PTT_KEY])
        self.ptt_key_name = ptt_key_name
        self.is_recording = False
        self.processing = False

    def on_key_press(self, key):
        if key == self.ptt_key and not self.is_recording and not self.processing:
            self.is_recording = True
            if not self.recorder.start():
                self.is_recording = False
                return
            print("  🔴 Recording...", end="", flush=True)

    def on_key_release(self, key):
        if key == self.ptt_key and self.is_recording:
            self.is_recording = False
            audio_data, duration = self.recorder.stop()

            if audio_data is None:
                print(" (too short, ignored)")
                return

            print(f" stopped ({duration:.1f}s)")
            self.processing = True

            # Process in background thread to not block key listener
            threading.Thread(target=self._process, args=(audio_data,), daemon=True).start()

    def _process(self, audio_data):
        try:
            print("  ⏳ Transcribing...", end="", flush=True)
            start = time.time()
            text = self.stt.transcribe(audio_data)
            elapsed = time.time() - start

            if text:
                print(f" done ({elapsed:.1f}s)")
                print(f"  📝 \"{text}\"")
                paste_text(text)
                print("  ✅ Pasted!")

                # macOS notification sound
                subprocess.run(["afplay", "/System/Library/Sounds/Pop.aiff"], capture_output=True)
            else:
                print(" (empty result)")
        except Exception as e:
            print(f"\n  ❌ Error: {e}")
        finally:
            self.processing = False

    def run(self):
        ptt_display = self.ptt_key_name.replace("_", " ").title()
        print("━" * 50)
        print(f"🎤 VoiceKey v{__version__}")
        print("━" * 50)
        print(f"  PTT Key:  {ptt_display}")
        print(f"  Mic:      {self.recorder.device_name}")
        print(f"  Hold key to record, release to transcribe.")
        print(f"  Result is auto-pasted to current app.")
        print(f"  Press Ctrl+C to quit.")
        print("━" * 50)
        print()

        # macOS permission reminder
        print("⚠️  Make sure to allow:")
        print("   • Accessibility: System Settings → Privacy → Accessibility")
        print("   • Microphone: System Settings → Privacy → Microphone")
        print()

        with keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release,
        ) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\n\n👋 Bye!")


# ─── Entry Point ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="VoiceKey - Speech to Text for Vibe Coding")
    parser.add_argument(
        "--key", 
        choices=list(KEY_MAP.keys()), 
        default=DEFAULT_PTT_KEY,
        help=f"PTT key (default: {DEFAULT_PTT_KEY})"
    )
    parser.add_argument("--setup", action="store_true", help="Re-enter API key")
    args = parser.parse_args()

    api_key = setup_api_key(force=args.setup)

    if not api_key:
        print("❌ No API key configured. Run: python voicekey.py --setup")
        sys.exit(1)

    app = VoiceKey(api_key=api_key, ptt_key_name=args.key)
    app.run()


if __name__ == "__main__":
    main()
