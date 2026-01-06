"""PTY wrapper for Claude Code."""

import os
import sys
import threading
from typing import IO, Any

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import msvcrt

    from winpty import PtyProcess  # type: ignore[import-not-found]
else:
    import signal
    import termios
    import tty
    from types import FrameType

    import pexpect


class ClaudePTY:
    """Spawns and controls Claude Code in a pseudo-terminal."""

    # How much terminal output to keep for context
    SCREEN_BUFFER_SIZE = 4000

    # Lines reserved for status bar at bottom
    STATUS_BAR_LINES = 2

    # Debug: log escape sequences to file
    DEBUG_ESCAPES = False

    def __init__(self) -> None:
        self.process: Any = None
        self.output_thread: threading.Thread | None = None
        self.input_thread: threading.Thread | None = None
        self.running = False
        self.old_tty_settings: Any = None
        self._screen_buffer = ""
        self._buffer_lock = threading.Lock()
        self.term_lines = 24
        self.term_cols = 80
        self._debug_file: IO[str] | None = None
        self._esc_buffer = ""  # Buffer for collecting escape sequences
        # Status bar state for redrawing after scroll region resets
        self._status_line1 = ""
        self._status_line2 = ""
        self._pty_lines = 24  # Lines available to PTY (minus status bar)
        # Flag to redraw status bar after output settles
        self._needs_status_redraw = False

    def start(self, args: list[str] | None = None) -> None:
        """Start Claude Code in a PTY.

        Args:
            args: Command-line arguments to pass to claude (e.g., ["--continue"])
        """
        # Get actual terminal size
        try:
            size = os.get_terminal_size()
            self.term_lines = size.lines
            self.term_cols = size.columns
        except OSError:
            self.term_lines = 24
            self.term_cols = 80

        # Reserve bottom lines for status bar
        self._pty_lines = self.term_lines - self.STATUS_BAR_LINES

        if IS_WINDOWS:
            self._start_windows(args)
        else:
            self._start_unix(args)

        self.running = True

        # Start output reader thread
        self.output_thread = threading.Thread(target=self._read_output, daemon=True)
        self.output_thread.start()

        # Start input reader thread
        self.input_thread = threading.Thread(target=self._read_input, daemon=True)
        self.input_thread.start()

    def _start_windows(self, args: list[str] | None = None) -> None:
        """Start Claude Code on Windows using pywinpty."""
        import shutil

        # Find full path to claude executable
        claude_path = shutil.which("claude")
        if not claude_path:
            raise FileNotFoundError("Claude Code not found in PATH")

        # Build command string for pywinpty
        cmd = claude_path
        if args:
            # Quote args that contain spaces
            quoted_args = []
            for arg in args:
                if " " in arg:
                    quoted_args.append(f'"{arg}"')
                else:
                    quoted_args.append(arg)
            cmd = cmd + " " + " ".join(quoted_args)

        # Use original working directory if set by launcher
        original_cwd = os.environ.get("VOICE_CLAUDE_ORIGINAL_CWD")

        # Use pywinpty for true PTY support on Windows
        self.process = PtyProcess.spawn(
            cmd,
            dimensions=(self._pty_lines, self.term_cols),
            cwd=original_cwd,
        )

    def _start_unix(self, args: list[str] | None = None) -> None:
        """Start Claude Code on Unix using PTY."""
        dimensions = (self._pty_lines, self.term_cols)

        # Set scroll region to protect status bar area
        sys.stdout.write(f"\x1b[1;{self._pty_lines}r")
        sys.stdout.flush()

        # Register resize handler
        signal.signal(signal.SIGWINCH, self._handle_resize)

        # Use original working directory if set by launcher
        original_cwd = os.environ.get("VOICE_CLAUDE_ORIGINAL_CWD")

        self.process = pexpect.spawn(
            "claude",
            args=args or [],
            encoding="utf-8",
            dimensions=dimensions,
            cwd=original_cwd,
        )

        # Open debug file
        if self.DEBUG_ESCAPES:
            self._debug_file = open("/tmp/claude_escapes.log", "w")

        # Put terminal in raw mode for keyboard passthrough
        try:
            self.old_tty_settings = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
        except termios.error:
            self.old_tty_settings = None

    def _read_output(self) -> None:
        """Read and print Claude Code output in real-time."""
        if IS_WINDOWS:
            self._read_output_windows()
        else:
            self._read_output_unix()

    def _read_output_windows(self) -> None:
        """Read output on Windows using pywinpty."""
        import re
        import time

        # Pattern to filter terminal capability responses (DA1, DA2, etc.)
        da_pattern = re.compile(r'\x1b\[\?[0-9;]*c')

        while self.running and self.process:
            try:
                if not self.process.isalive():
                    self.running = False
                    break

                # Read available data from PTY
                data = self.process.read(1024)
                if data:
                    # Filter out Device Attributes responses
                    data = da_pattern.sub('', data)
                    if data:
                        sys.stdout.write(data)
                        sys.stdout.flush()

                        # Add to screen buffer
                        with self._buffer_lock:
                            self._screen_buffer += data
                            if len(self._screen_buffer) > self.SCREEN_BUFFER_SIZE:
                                self._screen_buffer = self._screen_buffer[
                                    -self.SCREEN_BUFFER_SIZE:
                                ]
                else:
                    # No data available, small sleep to prevent CPU spinning
                    time.sleep(0.01)
            except EOFError:
                self.running = False
                break
            except Exception:
                self.running = False
                break

    def _read_output_unix(self) -> None:
        """Read output on Unix."""
        while self.running and self.process:
            try:
                # Read one character at a time for immediate output
                char = self.process.read_nonblocking(size=1, timeout=0.1)
                sys.stdout.write(char)
                sys.stdout.flush()

                # Track escape sequences for scroll region restoration
                self._track_escape_sequence(char)

                # Add to screen buffer
                with self._buffer_lock:
                    self._screen_buffer += char
                    # Trim if too long
                    if len(self._screen_buffer) > self.SCREEN_BUFFER_SIZE:
                        self._screen_buffer = self._screen_buffer[
                            -self.SCREEN_BUFFER_SIZE:
                        ]

            except pexpect.TIMEOUT:
                # No output for a moment - good time to redraw status bar if needed
                if self._needs_status_redraw and self._status_line1:
                    self._needs_status_redraw = False
                    self.draw_status_bar(self._status_line1, self._status_line2)
                continue
            except pexpect.EOF:
                self.running = False
                self._restore_terminal()
                break
            except Exception:
                self._restore_terminal()
                break

    def _read_input(self) -> None:
        """Read keyboard input and forward to Claude Code."""
        if IS_WINDOWS:
            self._read_input_windows()
        else:
            self._read_input_unix()

    def _read_input_windows(self) -> None:
        """Read input on Windows using msvcrt."""
        while self.running:
            try:
                if msvcrt.kbhit():  # type: ignore[attr-defined]
                    # Read character (supports special keys)
                    char = msvcrt.getwch()  # type: ignore[attr-defined]

                    # Handle special keys (arrow keys, etc.)
                    if char in ('\x00', '\xe0'):
                        # Extended key - read the second byte
                        char2 = msvcrt.getwch()  # type: ignore[attr-defined]
                        # Map Windows virtual keys to ANSI sequences
                        key_map = {
                            'H': '\x1b[A',  # Up
                            'P': '\x1b[B',  # Down
                            'M': '\x1b[C',  # Right
                            'K': '\x1b[D',  # Left
                            'G': '\x1b[H',  # Home
                            'O': '\x1b[F',  # End
                            'S': '\x1b[3~', # Delete
                        }
                        data = key_map.get(char2, '')
                    else:
                        data = char

                    if data and self.process and self.running:
                        self.process.write(data)
                else:
                    # Small sleep to prevent CPU spinning
                    import time
                    time.sleep(0.01)
            except Exception:
                break

    def _read_input_unix(self) -> None:
        """Read input on Unix."""
        fd = sys.stdin.fileno()
        while self.running:
            try:
                # Read available input
                raw_data = os.read(fd, 1024)
                if not raw_data:
                    break
                data = raw_data.decode("utf-8", errors="ignore")

                # Filter out mouse escape sequences
                # Mouse events: ESC[M..., ESC[<...M, ESC[<...m
                if "\x1b[M" in data or "\x1b[<" in data:
                    continue

                if self.process and self.running:
                    self.process.send(data)
            except OSError:
                break
            except Exception:
                break

    def get_screen_state(self) -> str:
        """Get recent terminal output for context."""
        with self._buffer_lock:
            # Return a cleaned version - strip ANSI codes for readability
            import re
            text = self._screen_buffer
            # Remove ANSI escape sequences
            text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
            text = re.sub(r'\x1b\][^\x07]*\x07', '', text)  # OSC sequences
            # Keep last ~50 lines
            lines = text.split('\n')
            return '\n'.join(lines[-50:])

    def has_menu_prompt(self) -> bool:
        """Best-effort detection of selection/menu prompts."""
        text = self.get_screen_state()
        if "❯" in text:
            return True
        import re
        # Common yes/no style prompts
        if re.search(r'\[(?:y/n|Y/N|yes/no|Yes/No)\]', text):
            return True
        # Numbered options combined with permission-like wording
        if re.search(r'(?m)^\s*\d+\.\s+\w+', text) and re.search(
            r'\b(allow|deny|approve|reject|permission|permit|grant|refuse)\b',
            text,
            flags=re.IGNORECASE,
        ):
            return True
        return False

    def _restore_terminal(self) -> None:
        """Restore terminal settings to normal mode."""
        if IS_WINDOWS:
            # Windows doesn't need terminal restoration
            pass
        else:
            if self.old_tty_settings:
                try:
                    termios.tcsetattr(
                        sys.stdin, termios.TCSADRAIN, self.old_tty_settings
                    )
                    self.old_tty_settings = None
                except termios.error:
                    pass
            # Reset scroll region to full terminal and clear screen
            sys.stdout.write("\x1b[r")  # Reset scroll region
            sys.stdout.write("\x1b[2J")  # Clear entire screen
            sys.stdout.write("\x1b[H")  # Move cursor to top-left
            sys.stdout.flush()

    def _handle_resize(self, signum: int, frame: "FrameType | None") -> None:
        """Handle terminal resize signal (Unix only)."""
        try:
            size = os.get_terminal_size()
            old_pty_lines = self._pty_lines
            self.term_lines = size.lines
            self.term_cols = size.columns
            self._pty_lines = self.term_lines - self.STATUS_BAR_LINES

            # When shrinking, we need to clear areas that will be outside new boundaries
            # to prevent visual corruption
            if self._pty_lines < old_pty_lines:
                # Save cursor, clear from new bottom to old bottom, restore cursor
                output = "\x1b[s"  # Save cursor
                # Clear lines that are now outside the PTY area
                for line in range(self._pty_lines + 1, old_pty_lines + 1):
                    output += f"\x1b[{line};1H\x1b[2K"
                output += "\x1b[u"  # Restore cursor
                sys.stdout.write(output)

            # Update scroll region
            sys.stdout.write(f"\x1b[1;{self._pty_lines}r")
            sys.stdout.flush()

            # Tell Claude Code about new size
            if self.process:
                self.process.setwinsize(self._pty_lines, self.term_cols)

            # Schedule status bar redraw after Claude Code's output settles
            self._needs_status_redraw = True
        except OSError:
            pass

    def send(self, text: str) -> None:
        """Send text input to Claude Code."""
        import time

        if not self.process or not self.running:
            return
        if IS_WINDOWS:
            # Send text first, pause, then send Enter separately
            self.process.write(text)
            time.sleep(0.2)
            self.process.write("\r")
        else:
            self.process.send(text)
            self.process.send("\r")

    def send_key(self, key: str) -> None:
        """Send a special key to Claude Code."""
        if not self.process or not self.running:
            return

        # Map key names to escape sequences
        key_map = {
            "enter": "\r",
            "return": "\r",
            "escape": "\x1b",
            "esc": "\x1b",
            "up": "\x1b[A",
            "down": "\x1b[B",
            "right": "\x1b[C",
            "left": "\x1b[D",
            "tab": "\t",
            "shift+tab": "\x1b[Z",  # Reverse tab
            "backtab": "\x1b[Z",
            "backspace": "\x7f",
            "delete": "\x1b[3~",
            "home": "\x1b[H",
            "end": "\x1b[F",
        }

        # Check if it's a named key
        key_lower = key.lower()
        if key_lower in key_map:
            data = key_map[key_lower]
        elif len(key) == 1:
            # Single character - just send it without enter
            data = key
        else:
            # Unknown key name - send as-is
            data = key

        if IS_WINDOWS:
            self.process.write(data)
        else:
            self.process.send(data)

    def send_keys(self, keys: list[str], delay: float = 0.05) -> None:
        """Send a sequence of keys with small delays between them."""
        import time
        for key in keys:
            self.send_key(key)
            time.sleep(delay)

    def send_escape(self) -> None:
        """Send Escape key to interrupt Claude Code."""
        if not self.process or not self.running:
            return
        self.send_key("escape")

    def send_interrupt(self) -> None:
        """Send Ctrl+C to Claude Code."""
        if not self.process or not self.running:
            return
        if IS_WINDOWS:
            self.process.write("\x03")
        else:
            self.process.sendcontrol("c")

    def stop(self) -> None:
        """Stop Claude Code."""
        self.running = False
        self._restore_terminal()

        if self.process:
            if IS_WINDOWS:
                self.process.terminate()
            else:
                self.process.close()

    def is_alive(self) -> bool:
        """Check if Claude Code is still running."""
        if not self.process:
            return False
        return bool(self.process.isalive())

    def _track_escape_sequence(self, char: str) -> None:
        """Track escape sequences to detect scroll region resets."""
        if char == '\x1b':
            # Start of escape sequence
            self._esc_buffer = char
        elif self._esc_buffer:
            self._esc_buffer += char
            # Check if sequence is complete (ends with letter)
            if char.isalpha() or char == '~':
                seq = self._esc_buffer
                # Log interesting sequences
                if self.DEBUG_ESCAPES and self._debug_file:
                    if '[r' in seq or '?1049' in seq or '[2J' in seq or '[H' in seq:
                        self._debug_file.write(f"ESC: {repr(seq)}\n")
                        self._debug_file.flush()
                # Detect scroll region reset and restore ours
                if seq == '\x1b[r':
                    self._restore_status_bar()
                self._esc_buffer = ""
            # Safety: don't buffer forever
            elif len(self._esc_buffer) > 20:
                self._esc_buffer = ""

    def _restore_status_bar(self) -> None:
        """Restore scroll region and redraw status bar after Claude Code resets it."""
        # Restore our scroll region
        sys.stdout.write(f"\x1b[1;{self._pty_lines}r")
        sys.stdout.flush()
        # Redraw status bar if we have content
        if self._status_line1:
            self.draw_status_bar(self._status_line1, self._status_line2)

    def draw_status_bar(self, line1: str, line2: str = "") -> None:
        """Draw status bar in the reserved bottom lines.

        Args:
            line1: Main status text (e.g., "🎤 Listening...")
            line2: Detail text (e.g., agent action info)
        """
        if not self.running:
            return

        # Store for redrawing after scroll region resets
        self._status_line1 = line1
        self._status_line2 = line2

        # Save cursor position
        output = "\x1b[s"

        # Status bar starts at (term_lines - 1)
        status_line1 = self.term_lines - 1
        status_line2 = self.term_lines

        # Draw line 1: clear line, write content
        output += f"\x1b[{status_line1};1H"  # Move to line
        output += "\x1b[2K"  # Clear line
        output += "\x1b[30;47m"  # Black text on white background
        output += f" {line1:<{self.term_cols - 1}}"[:self.term_cols]  # Pad/truncate
        output += "\x1b[0m"  # Reset formatting

        # Draw line 2: clear line, write content
        output += f"\x1b[{status_line2};1H"
        output += "\x1b[2K"
        output += "\x1b[97m"  # Bright white text
        output += f" {line2:<{self.term_cols - 1}}"[:self.term_cols]
        output += "\x1b[0m"

        # Restore cursor position
        output += "\x1b[u"

        sys.stdout.write(output)
        sys.stdout.flush()
