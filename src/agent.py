"""Intermediary agent that interprets voice commands."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from api_client import ClaudeAPIClient

# Debug log file
# Unix: tail -f /tmp/voice-claude-agent.log
# Windows: Get-Content $env:TEMP\voice-claude-agent.log -Wait
DEBUG_LOG = Path(tempfile.gettempdir()) / "voice-claude-agent.log"

SYSTEM_PROMPT = """\
You are a PASS-THROUGH interface that translates voice input into terminal actions.
You do NOT solve tasks.

YOUR ONLY JOB:
1. Read the voice transcript
2. Look at the terminal state
3. Decide: menu navigation (send_keys) OR pass-through text (send_text)

RULES FOR send_text:
- Send the user's EXACT words from the transcript
- Do NOT interpret what they mean
- Do NOT convert requests into commands
- Do NOT solve their task for them
- Only fix obvious speech-to-text errors (e.g., "list the files" not "leased the piles")

EXAMPLES OF CORRECT BEHAVIOR:
User says: "list all the files in this folder"
WRONG: send_text("ls -la")  ← You are solving the task!
CORRECT: send_text("list all the files in this folder")  ← Pass through exactly

User says: "create a new Python file called main dot py"
WRONG: send_text("touch main.py")  ← You are interpreting!
CORRECT: send_text("create a new Python file called main.py")  ← Exact words

User says: "slash command exit"
CORRECT: send_text("/exit")  ← This is a special command syntax

MENU NAVIGATION:
When terminal shows a menu with ❯ marker:
  ❯ 1. Yes
    2. No
Then use send_keys (ArrowDown, Enter, Esc, etc.) to navigate.

Do NOT use send_keys("y") as confirmation. Use send_keys("enter") instead.

YOU ARE A MICROPHONE, NOT AN ASSISTANT.
Claude Code is the assistant - let IT interpret the user's intent.
"""

TOOLS = [
    {
        "name": "send_text",
        "description": (
            "Send text to Claude Code as if typed, then press Enter. "
            "Use for regular instructions and prompts. "
            "Use the original user's message. Small typos may be corrected."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to send to Claude Code",
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "send_keys",
        "description": (
            "Send a sequence of key presses for navigation and selection. "
            "Use for menu navigation, confirmations, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of keys to press in order. Valid keys: 'enter', "
                        "'escape', 'up', 'down', 'left', 'right', 'tab', "
                        "'shift+tab', or any single character."
                    ),
                }
            },
            "required": ["keys"],
        },
    },
    {
        "name": "send_escape",
        "description": (
            "Send Escape key to interrupt/cancel. "
            "Use when user says stop, wait, cancel, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


class Agent:
    """Interprets voice commands and decides actions for Claude Code."""

    def __init__(self, api_client: ClaudeAPIClient, debug: bool = True):
        self.api_client = api_client
        self.processing = False
        self.debug = debug
        # Clear log on start
        if self.debug:
            DEBUG_LOG.write_text("")

    def _log(self, msg: str, data: Any = None) -> None:
        """Write to debug log file."""
        if not self.debug:
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {msg}"
        if data is not None:
            line += f"\n{json.dumps(data, indent=2)}"
        line += "\n"
        with open(DEBUG_LOG, "a") as f:
            f.write(line)

    def process(
        self, transcript: str, terminal_state: str = ""
    ) -> dict[str, Any] | None:
        """
        Process a voice transcript and decide what action to take.

        Args:
            transcript: The transcribed voice command
            terminal_state: Current terminal screen content (optional)

        Returns:
            Dict with 'tool' and 'args' keys, or None if processing was cancelled
        """
        self.processing = True
        self._log(f">>> Received transcript: \"{transcript}\"")

        try:
            # Build the user message
            user_content = f"Voice transcript: {transcript}"
            if terminal_state:
                user_content += f"\n\nTerminal state:\n```\n{terminal_state}\n```"

            messages = [{"role": "user", "content": user_content}]

            self._log("Calling Claude API...")
            response = self.api_client.send_message(
                messages=messages,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                max_tokens=256,
            )
            self._log("API response:", response)

            # Extract tool use from response
            for block in response.get("content", []):
                if block.get("type") == "tool_use":
                    result = {
                        "tool": block["name"],
                        "args": block.get("input", {}),
                    }
                    self._log(f"<<< Decision: {result['tool']}", result["args"])
                    return result

            # No tool use found - shouldn't happen with tool_choice, but handle it
            # Default to sending the transcript as text
            self._log("<<< No tool use in response, defaulting to send_text")
            return {"tool": "send_text", "args": {"text": transcript}}

        except Exception as e:
            # On error, fall back to sending transcript as text
            self._log(f"!!! Error: {e}")
            return {"tool": "send_text", "args": {"text": transcript}}

        finally:
            self.processing = False

    def cancel(self) -> None:
        """Cancel current processing."""
        self.processing = False
        self.api_client.cancel_request()
