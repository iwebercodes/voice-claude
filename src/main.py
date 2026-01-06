#!/usr/bin/env python3
"""Voice-controlled Claude Code with intermediary agent."""

import atexit
import shutil
import signal
import sys
import threading
import time
from enum import Enum, auto
from typing import Any

from agent import Agent
from api_client import ClaudeAPIClient
from audio import AudioCapture
from claude_pty import ClaudePTY
from transcribe import Transcriber


class State(Enum):
    LISTENING = auto()
    SPEAKING = auto()
    TRANSCRIBING = auto()
    AGENT_PROCESSING = auto()
    CLAUDE_WORKING = auto()


class VoiceClaude:
    """Main controller for voice-controlled Claude Code."""

    # Status display for each state
    STATE_DISPLAY = {
        State.LISTENING: "🎤 Listening...",
        State.SPEAKING: "👤 Speaking...",
        State.TRANSCRIBING: "📝 Transcribing...",
        State.AGENT_PROCESSING: "🤔 Processing...",
        State.CLAUDE_WORKING: "⚡ Working",
    }

    def __init__(self, claude_args: list[str] | None = None) -> None:
        self.state = State.LISTENING
        self.state_lock = threading.Lock()
        self.claude_args = claude_args or []

        # Components
        self.capture: AudioCapture | None = None
        self.transcriber: Transcriber | None = None
        self.claude: ClaudePTY | None = None
        self.api_client: ClaudeAPIClient | None = None
        self.agent: Agent | None = None

        # For interrupt handling
        self.pending_transcript: str | None = None
        self.should_interrupt = False

        # For status bar display
        self.last_action = ""

    def initialize(self) -> None:
        """Initialize all components."""
        print("Initializing voice-controlled Claude Code...")
        print()

        # Audio capture
        self.capture = AudioCapture()

        # Transcriber
        self.transcriber = Transcriber()

        # Claude PTY
        self.claude = ClaudePTY()

        # Clear terminal before starting Claude Code
        print("\033[2J\033[H", end="", flush=True)
        self.claude.start(args=self.claude_args)

        # Wait for Claude Code to initialize (and refresh token if needed)
        time.sleep(1.0)

        # API client for agent - initialized AFTER Claude Code starts
        # so we use any freshly refreshed OAuth token
        self.api_client = ClaudeAPIClient()
        self.api_client.initialize()

        # Agent
        self.agent = Agent(self.api_client)

    def set_state(self, state: State, detail: str | None = None) -> None:
        """Thread-safe state update with status bar refresh."""
        with self.state_lock:
            self.state = state

        # Update status bar
        if self.claude and self.claude.running:
            status = self.STATE_DISPLAY.get(state, str(state))
            detail_text = detail if detail is not None else self.last_action
            self.claude.draw_status_bar(status, detail_text)

    def get_state(self) -> State:
        """Thread-safe state read."""
        with self.state_lock:
            return self.state

    def _on_speech_start(self) -> None:
        """Called when user starts speaking."""
        self.set_state(State.SPEAKING)
        # Send ESC only if Claude is generating, not if showing a menu/dialog
        if self.claude:
            if not self.claude.has_menu_prompt():
                self.claude.send_escape()

    def execute_action(self, action: dict[str, Any]) -> None:
        """Execute an action from the agent."""
        if not self.claude:
            return

        tool = action["tool"]
        args = action.get("args", {})

        if tool == "send_text":
            self.claude.send(args.get("text", ""))
        elif tool == "send_keys":
            keys = args.get("keys", [])
            self.claude.send_keys(keys)
        elif tool == "send_key":
            # Legacy single key support
            self.claude.send_key(args.get("key", ""))
        elif tool == "send_escape":
            self.claude.send_escape()

    def run(self) -> None:
        """Main loop."""
        if not (self.claude and self.capture and self.transcriber and self.agent):
            return

        # Draw initial status bar
        self.set_state(State.LISTENING, "Ready")

        while self.claude.is_alive():
            self.set_state(State.LISTENING)

            # Listen for speech
            audio = self.capture.listen(
                should_stop=lambda: not self.claude.is_alive() if self.claude else True,
                on_speech_start=self._on_speech_start
            )

            if audio is None:
                continue

            # Transcribe
            self.set_state(State.TRANSCRIBING)
            text = self.transcriber.transcribe(audio)

            if not text:
                continue

            # Process with agent (pass terminal state for context)
            self.set_state(State.AGENT_PROCESSING, f'"{text}"')
            terminal_state = self.claude.get_screen_state()
            action = self.agent.process(text, terminal_state)

            if action:
                # Format action for display: tool_name(args)
                tool = action["tool"]
                args = action.get("args", {})
                if tool == "send_text":
                    detail = f'send_text("{args.get("text", "")}")'
                elif tool == "send_keys":
                    keys = args.get("keys", [])
                    detail = f'send_keys({keys})'
                elif tool == "send_escape":
                    detail = "send_escape()"
                else:
                    detail = f"{tool}({args})"

                # Store for display after returning to listening
                self.last_action = detail
                self.set_state(State.CLAUDE_WORKING, detail)
                self.execute_action(action)

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.claude:
            self.claude.stop()
        if self.api_client:
            self.api_client.close()


def main() -> None:
    # Check claude command exists
    if not shutil.which("claude"):
        print(
            "Error: Claude Code not found.\n"
            "Install: curl -fsSL https://claude.ai/install.sh | bash\n"
            "Then run 'claude' once to authenticate.",
            file=sys.stderr
        )
        sys.exit(1)

    # Forward all CLI arguments to claude
    claude_args = sys.argv[1:]

    app = VoiceClaude(claude_args=claude_args)

    # Track if cleanup has already run to avoid double cleanup
    cleanup_done = False

    def do_cleanup() -> None:
        nonlocal cleanup_done
        if not cleanup_done:
            cleanup_done = True
            app.cleanup()

    # Register cleanup for normal exit
    atexit.register(do_cleanup)

    # Unix: handle SIGTERM (kill command) for graceful shutdown
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        app.initialize()
        app.run()
    except KeyboardInterrupt:
        pass
    # atexit handles cleanup


if __name__ == "__main__":
    main()
