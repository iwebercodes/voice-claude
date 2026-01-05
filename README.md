# Voice Claude

Voice input wrapper for [Claude Code](https://code.claude.com/docs). Speak to your terminal instead of typing.

---

**[Connect with me on LinkedIn](https://www.linkedin.com/in/ilja-weber-bb7135b5)** - I'm building more voice-powered dev tools and would love to hear your ideas. Drop me a message with your feedback, feature requests, or just say hi!

---

```
Microphone → Whisper STT → Claude Agent → Claude Code → Terminal
```

Voice Claude captures your speech, transcribes it locally using Whisper, and sends commands to Claude Code running in a PTY. All Claude Code output appears in your terminal in real-time.

## Installation

### Requirements

- Python 3.10 or later
- [Claude Code](https://code.claude.com/docs) installed and authenticated
- Microphone

### macOS, Linux, WSL

```bash
curl -fsSL https://raw.githubusercontent.com/iwebercodes/voice-claude/master/install.sh | bash
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/iwebercodes/voice-claude/master/install.ps1 | iex
```

### Windows CMD

```cmd
curl -fsSL https://raw.githubusercontent.com/iwebercodes/voice-claude/master/install.cmd -o install.cmd && install.cmd && del install.cmd
```

### Manual Installation

```bash
git clone https://github.com/iwebercodes/voice-claude.git
cd voice-claude
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
voice-claude
```

Or run directly from the installation directory:

```bash
cd ~/.voice-claude
source venv/bin/activate
python3 -u src/main.py
```

The first run downloads the Whisper speech recognition model (~500MB).

### How It Works

1. Voice Claude starts Claude Code in the background
2. Speak into your microphone
3. Your speech is transcribed locally (nothing sent to external services)
4. An intermediary agent interprets your intent and sends appropriate commands to Claude Code
5. Claude Code's responses appear in your terminal

### Status Bar

A status bar at the bottom of the terminal shows the current state:
- **LISTENING** - Waiting for speech
- **SPEAKING** - Detecting voice input
- **TRANSCRIBING** - Converting speech to text
- **AGENT_PROCESSING** - Interpreting your command
- **CLAUDE_WORKING** - Claude Code is processing

## System Dependencies

The installer handles these automatically, but for manual installation:

**macOS (Homebrew):**
```bash
brew install portaudio
```

**Debian/Ubuntu:**
```bash
sudo apt-get install libportaudio2 portaudio19-dev
```

**Fedora/RHEL:**
```bash
sudo dnf install portaudio portaudio-devel
```

**Arch Linux:**
```bash
sudo pacman -S portaudio
```

## Troubleshooting

### "Claude Code not found"

Install Claude Code first:
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Then run `claude` once to authenticate before using Voice Claude.

### Microphone not working

Make sure your system's default audio input is set to the correct microphone. Voice Claude uses the system default.

### Whisper model download fails

The model is downloaded from Hugging Face. If you're behind a proxy or firewall, you may need to configure `HF_HOME` or download the model manually.

## License

MIT
