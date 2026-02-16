# 🎤 VoiceKey

Lightweight Speech-to-Text tool for Vibe Coding.  
Hold a key → Speak → Release → Text is auto-pasted.

## Quick Start

```bash
# 1. Setup
cd voicekey
bash setup.sh

# 2. Run
source .venv/bin/activate
python voicekey.py
```

First run will ask for your **OpenAI API key**.  
Get one at: https://platform.openai.com/api-keys

## Usage

1. Run the app
2. Open any app (terminal, IDE, browser, etc.)
3. **Hold Right Option (⌥) key** and speak
4. Release the key → text is transcribed and pasted

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

On first run, macOS will ask for:
- **Accessibility**: System Settings → Privacy & Security → Accessibility → Allow Terminal/iTerm
- **Microphone**: System Settings → Privacy & Security → Microphone → Allow Terminal/iTerm

## How It Works

```
Hold PTT Key → Mac Microphone → OpenAI Whisper API → Clipboard → Auto Paste
```

- Audio: 16kHz, 16-bit, mono WAV
- STT: OpenAI Whisper API (supports Korean + English mixed speech)
- Output: pbcopy + Cmd+V simulation
- Cost: ~$0.006/min (~$10/month for heavy use)

## Config

Stored at `~/.voicekey/config.json`

```json
{
  "openai_api_key": "sk-..."
}
```
