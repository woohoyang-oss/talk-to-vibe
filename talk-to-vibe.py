#!/usr/bin/env python3
"""
Talk to Vibe - Lightweight Speech-to-Text for Vibe Coding
Hold Right Option key → Record → Release → Transcribe → Paste

Supports multiple STT providers: Groq (free), OpenAI, Custom/Local

Usage:
    python talk-to-vibe.py                # Run with default settings
    python talk-to-vibe.py --key cmd_r    # Use Right Cmd as PTT key
    python talk-to-vibe.py --setup        # Re-configure provider & API key
    python talk-to-vibe.py --provider openai  # One-off provider override
"""

__version__ = "0.3.0"

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
except ImportError:
    print("❌ Missing dependencies. Run: bash setup.sh")
    sys.exit(1)

# ─── Config ─────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".talktovibe"
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

# ─── Provider Registry ──────────────────────────────────────────
PROVIDERS = {
    "groq": {
        "name": "Groq Whisper (free, fast)",
        "key_prefix": "gsk_",
        "key_url": "https://console.groq.com/keys",
        "pkg": "groq",
    },
    "openai": {
        "name": "OpenAI Whisper (paid)",
        "key_prefix": "sk-",
        "key_url": "https://platform.openai.com/api-keys",
        "pkg": "openai",
    },
    "custom": {
        "name": "Custom / Local (OpenAI-compatible endpoint)",
        "key_prefix": None,
        "key_url": None,
        "pkg": "openai",
    },
}

DEFAULT_PROVIDER = "groq"


# ─── Config Management ─────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config):
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    CONFIG_FILE.chmod(0o600)  # Owner read/write only (contains API keys)


def _input_safe(prompt):
    """Input with graceful Ctrl+C / EOF handling."""
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n   Cancelled.")
        sys.exit(0)


def _ask_api_key(provider_info):
    """Ask user for an API key with prefix validation."""
    prefix = provider_info["key_prefix"]
    url = provider_info["key_url"]

    if url:
        print(f"   Get your key at: {url}")

    while True:
        api_key = _input_safe("   Enter API key: ")

        if not api_key:
            print("   ⚠️  API key cannot be empty. Try again.")
            continue

        if prefix and not api_key.startswith(prefix):
            print(f"   ⚠️  Expected key starting with '{prefix}'. Are you sure? (y/n) ", end="")
            confirm = _input_safe("")
            if confirm.lower() != "y":
                continue

        return api_key


def setup_provider(force=False):
    """Interactive provider setup wizard. Returns (provider_name, config)."""
    config = load_config()

    # Backward compatibility: existing groq_api_key without provider → assume groq
    if not force and "groq_api_key" in config:
        provider = config.get("provider", "groq")
        config["provider"] = provider
        return provider, config

    # Check if already configured
    if not force and "provider" in config:
        return config["provider"], config

    print("\n🔧 STT Provider Setup\n")
    print("   Choose your Speech-to-Text provider:\n")

    provider_list = list(PROVIDERS.keys())
    for i, key in enumerate(provider_list, 1):
        info = PROVIDERS[key]
        print(f"   {i}) {info['name']}")

    print()
    while True:
        choice = _input_safe(f"   Select provider [1-{len(provider_list)}]: ")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(provider_list):
                break
        except ValueError:
            pass
        print(f"   ⚠️  Enter a number between 1 and {len(provider_list)}")

    provider = provider_list[idx]
    provider_info = PROVIDERS[provider]
    print(f"\n   Selected: {provider_info['name']}\n")

    if provider == "groq":
        api_key = _ask_api_key(provider_info)
        config["provider"] = "groq"
        config["groq_api_key"] = api_key

    elif provider == "openai":
        api_key = _ask_api_key(provider_info)
        config["provider"] = "openai"
        config["openai_api_key"] = api_key

    elif provider == "custom":
        print("   Configure your OpenAI-compatible endpoint:\n")
        base_url = _input_safe("   Base URL (e.g. http://localhost:8000/v1): ")
        if not base_url:
            print("   ⚠️  Base URL is required for custom provider.")
            sys.exit(1)

        api_key = _input_safe("   API key (leave empty if not needed): ")
        model = _input_safe("   Model name (default: whisper-1): ")

        config["provider"] = "custom"
        config["custom_base_url"] = base_url
        config["custom_api_key"] = api_key or ""
        config["custom_model"] = model or "whisper-1"

    # PTT key selection
    print("\n🎹 Push-to-Talk Key Setup\n")
    key_list = list(KEY_MAP.keys())
    key_display = {
        "alt_r": "Right Option (⌥)",
        "alt_l": "Left Option (⌥)",
        "cmd_r": "Right Command (⌘)",
        "ctrl_r": "Right Control (⌃)",
        "f18": "F18",
        "f19": "F19",
        "f20": "F20",
    }
    current_key = config.get("ptt_key", DEFAULT_PTT_KEY)
    for i, key in enumerate(key_list, 1):
        label = key_display.get(key, key)
        default_mark = " (current)" if key == current_key else ""
        print(f"   {i}) {label}{default_mark}")

    print()
    while True:
        choice = _input_safe(f"   Select PTT key [1-{len(key_list)}] (Enter = keep current): ")
        if not choice:
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(key_list):
                config["ptt_key"] = key_list[idx]
                print(f"   Selected: {key_display.get(key_list[idx], key_list[idx])}")
                break
        except ValueError:
            pass
        print(f"   ⚠️  Enter a number between 1 and {len(key_list)}")

    save_config(config)
    print("   ✅ Saved to ~/.talktovibe/config.json\n")
    return provider, config


# ─── Audio Helpers ──────────────────────────────────────────────
def audio_to_wav_file(audio_data):
    """Save audio numpy array to a temporary WAV file. Caller must delete."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit = 2 bytes
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())
    return tmp.name


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


# ─── Audio Recorder ─────────────────────────────────────────────
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


# ─── STT Providers ──────────────────────────────────────────────
class GroqSTT:
    """Groq Whisper API (whisper-large-v3-turbo, free tier)."""

    def __init__(self, api_key):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.provider_name = "Groq"

    def transcribe(self, audio_data):
        wav_path = audio_to_wav_file(audio_data)
        try:
            with open(wav_path, "rb") as f:
                result = self.client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=f,
                )
            return result.text.strip()
        finally:
            os.unlink(wav_path)


class OpenAISTT:
    """OpenAI Whisper API (whisper-1, paid)."""

    def __init__(self, api_key):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.provider_name = "OpenAI"

    def transcribe(self, audio_data):
        wav_path = audio_to_wav_file(audio_data)
        try:
            with open(wav_path, "rb") as f:
                result = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                )
            return result.text.strip()
        finally:
            os.unlink(wav_path)


class CustomSTT:
    """Custom/Local OpenAI-compatible endpoint."""

    def __init__(self, base_url, api_key="", model="whisper-1"):
        from openai import OpenAI
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or "not-needed",
        )
        self.model = model
        self.provider_name = "Custom"

    def transcribe(self, audio_data):
        wav_path = audio_to_wav_file(audio_data)
        try:
            with open(wav_path, "rb") as f:
                result = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=f,
                )
            return result.text.strip()
        finally:
            os.unlink(wav_path)


def create_stt(provider, config):
    """Factory: create the right STT instance from provider name + config."""
    if provider == "groq":
        api_key = config.get("groq_api_key")
        if not api_key:
            print("❌ Groq API key not found. Run: python talk-to-vibe.py --setup")
            sys.exit(1)
        return GroqSTT(api_key)

    elif provider == "openai":
        api_key = config.get("openai_api_key")
        if not api_key:
            print("❌ OpenAI API key not found. Run: python talk-to-vibe.py --setup")
            sys.exit(1)
        return OpenAISTT(api_key)

    elif provider == "custom":
        base_url = config.get("custom_base_url")
        if not base_url:
            print("❌ Custom base URL not found. Run: python talk-to-vibe.py --setup")
            sys.exit(1)
        return CustomSTT(
            base_url=base_url,
            api_key=config.get("custom_api_key", ""),
            model=config.get("custom_model", "whisper-1"),
        )

    else:
        print(f"❌ Unknown provider: {provider}")
        sys.exit(1)


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
class TalkToVibe:
    def __init__(self, stt, ptt_key_name=DEFAULT_PTT_KEY):
        self.recorder = AudioRecorder()
        self.stt = stt
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
        print(f"🎤 Talk to Vibe v{__version__}")
        print("━" * 50)
        print(f"  PTT Key:   {ptt_display}")
        print(f"  Mic:       {self.recorder.device_name}")
        print(f"  Provider:  {self.stt.provider_name}")
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
    parser = argparse.ArgumentParser(description="Talk to Vibe - Speech to Text for Vibe Coding")
    parser.add_argument(
        "--key",
        choices=list(KEY_MAP.keys()),
        default=DEFAULT_PTT_KEY,
        help=f"PTT key (default: {DEFAULT_PTT_KEY})"
    )
    parser.add_argument("--setup", action="store_true", help="Re-configure STT provider & API key")
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
        help="One-off provider override (does not save to config)"
    )
    args = parser.parse_args()

    # Setup or load config
    provider, config = setup_provider(force=args.setup)

    # CLI provider override (one-off, not saved)
    if args.provider:
        provider = args.provider
        # If overriding and key missing, force setup for that provider
        if provider == "groq" and "groq_api_key" not in config:
            provider, config = setup_provider(force=True)
        elif provider == "openai" and "openai_api_key" not in config:
            provider, config = setup_provider(force=True)
        elif provider == "custom" and "custom_base_url" not in config:
            provider, config = setup_provider(force=True)

    # Create STT engine
    stt = create_stt(provider, config)

    # PTT key: CLI --key overrides config, config overrides default
    ptt_key = args.key
    if ptt_key == DEFAULT_PTT_KEY and "ptt_key" in config:
        ptt_key = config["ptt_key"]

    app = TalkToVibe(stt=stt, ptt_key_name=ptt_key)
    app.run()


if __name__ == "__main__":
    main()
