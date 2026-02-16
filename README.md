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
python talk-to-vibe.py
```

First run will ask you to choose an STT provider and enter your API key.

## STT Providers

| Provider | Model | Cost | Setup |
|----------|-------|------|-------|
| **Groq** (default) | whisper-large-v3-turbo | Free tier | [Get key](https://console.groq.com/keys) |
| **OpenAI** | whisper-1 | Paid | [Get key](https://platform.openai.com/api-keys) |
| **Custom / Local** | Any OpenAI-compatible | Varies | Your own endpoint |

### Switch Provider

```bash
python talk-to-vibe.py --setup           # Re-run setup wizard
python talk-to-vibe.py --provider openai # One-off override (not saved)
```

## Usage

1. Run the app in a terminal
2. Switch to any app (IDE, browser, Claude, etc.)
3. **Hold Right Option (⌥) key** and speak
4. Release the key → text is transcribed and pasted automatically

### Change PTT Key

```bash
python talk-to-vibe.py --key cmd_r    # Right Command
python talk-to-vibe.py --key ctrl_r   # Right Control
python talk-to-vibe.py --key f19      # F19 (if available)
```

Available keys: `alt_r`, `alt_l`, `cmd_r`, `ctrl_r`, `f18`, `f19`, `f20`

## macOS Permissions

On first run, grant these in **System Settings → Privacy & Security**:

- **Accessibility** → Allow your Terminal app
- **Microphone** → Allow your Terminal app

> Without Accessibility permission, auto-paste (Cmd+V simulation) will not work.

## How It Works

```
Hold PTT Key → Mac Microphone → STT Provider API → Clipboard → Auto Paste
```

- **STT Engine**: Groq, OpenAI, or any OpenAI-compatible endpoint
- **Audio**: 16kHz, 16-bit, mono WAV
- **Mic**: Auto-detects real hardware mic (skips virtual devices like BlackHole)
- **Output**: pbcopy + pynput Cmd+V simulation

## Config

Stored at `~/.talktovibe/config.json` (chmod 600)

```json
{
  "provider": "groq",
  "groq_api_key": "gsk_..."
}
```

Multi-provider example:
```json
{
  "provider": "custom",
  "groq_api_key": "gsk_...",
  "openai_api_key": "sk-...",
  "custom_base_url": "http://localhost:8000/v1",
  "custom_api_key": "",
  "custom_model": "whisper-1"
}
```

## License

MIT
