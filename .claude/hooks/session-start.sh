#!/bin/bash
set -euo pipefail

# Only run in Claude Code remote (web) environment
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Install PortAudio system library (required by sounddevice)
if ! dpkg -s libportaudio2 > /dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq libportaudio2 > /dev/null 2>&1
fi

# Install Python dependencies
pip install -q -r "$CLAUDE_PROJECT_DIR/requirements.txt"
