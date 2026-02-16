# 🎤 Talk to Vibe

Lightweight Speech-to-Text for macOS. Hold a key, speak, release — text is auto-pasted.

Built for vibe coding: dictate prompts, comments, commit messages, or anything else without leaving your keyboard.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/woohoyang-oss/talk-to-vibe.git
cd talk-to-vibe

# 2. Setup
bash setup.sh

# 3. Run
source .venv/bin/activate
python voicekey.py
```

First run will ask for your **Groq API key** (free).
Get one at: https://console.groq.com/keys

## Usage

1. Run the app in a terminal
2. Switch to any app (IDE, browser, Claude, etc.)
3. **Hold Right Option (⌥) key** and speak
4. Release the key → text is transcribed and pasted automatically

### Change PTT Key

```bash
python voicekey.py --key cmd_r    # Right Command
python voicekey.py --key ctrl_r   # Right Control
python voicekey.py --key f19      # F19 (if available)
```

Available keys: `alt_r`, `alt_l`, `cmd_r`, `ctrl_r`, `f18`, `f19`, `f20`

### Re-enter API Key

```bash
python voicekey.py --setup
```

## macOS Permissions

On first run, grant these in **System Settings → Privacy & Security**:

- **Accessibility** → Allow your Terminal app
- **Microphone** → Allow your Terminal app

> Without Accessibility permission, auto-paste (Cmd+V simulation) will not work.

## How It Works

```
Hold PTT Key → Mac Microphone → Groq Whisper API → Clipboard → Auto Paste
```

- **STT Engine**: Groq Whisper (`whisper-large-v3-turbo`) — fast, free tier available
- **Audio**: 16kHz, 16-bit, mono WAV
- **Mic**: Auto-detects real hardware mic (skips virtual devices like BlackHole)
- **Output**: pbcopy + pynput Cmd+V simulation
- **Cost**: Free (Groq free tier)

## Config

Stored at `~/.voicekey/config.json` (chmod 600)

```json
{
  "groq_api_key": "gsk_..."
}
```

## License

MIT
