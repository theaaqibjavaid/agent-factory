"""
Terminal sessions (Phase 5.1) — workspace-scoped PTY shells.

Each session forks a real shell (`sh`/`bash`) with its working directory
pinned inside the workspace sandbox root, so every command a user runs is
path-scoped to that workspace. Sessions support:

- write/resize over the PTY master fd
- a destructive-command guard: commands matching known destructive patterns
  (``rm -rf``, ``git push --force``, ``git reset --hard``, disk/format tools,
  fork bombs) are held back until the caller explicitly confirms them
- kill-on-close: closing the session terminates the child process group so no
  orphan shells survive a disconnect

The guard is defense-in-depth, not a security boundary: a user who can write
to the workspace can always run commands. It exists to stop accidental
one-keystroke destruction, mirroring ``docs/security.md`` guidance.
"""

import errno
import os
import pty
import select
import signal
import struct
import termios
import threading
import uuid
from queue import Empty, Queue
from typing import Dict, List, Optional

import structlog

logger = structlog.get_logger()

try:  # pragma: no cover - fcntl is POSIX-only
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]


# Destructive command patterns: (regex, explanation). The first line of input
# matching one of these requires explicit confirmation before execution.
_DESTRUCTIVE_PATTERNS: List[tuple] = [
    (r"rm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+", "recursive force delete (rm -rf)"),
    (r"\brm\s+-rf\b", "recursive force delete (rm -rf)"),
    (r"git\s+push\s+.*(--force|-f)(\s|$)", "force push over remote history"),
    (r"git\s+reset\s+--hard", "hard reset discards working tree changes"),
    (r"git\s+clean\s+(-[a-zA-Z]*f)", "force clean removes untracked files"),
    (r"\bmv\s+/\s+", "moving root filesystem"),
    (r"\bdd\s+if=", "raw block device write (dd)"),
    (r"\bmkfs(\.\w+)?\b", "filesystem formatting"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "system shutdown/reboot"),
    (r"\bchmod\s+(-[a-zA-Z]*R)?\s*[0-7]{3}\s+/", "recursive permission change on /"),
    (r":\(\)\s*\{", "fork bomb"),
    (r">\s*/dev/sd[a-z]+", "writing directly to a block device"),
]

_MAX_OUTPUT_BYTES = 64 * 1024  # per session output buffer


def is_destructive_command(line: str) -> Optional[str]:
    """Return a reason string if the line matches a destructive pattern."""
    import re

    stripped = line.strip()
    for pattern, reason in _DESTRUCTIVE_PATTERNS:
        if re.search(pattern, stripped):
            return reason
    return None


class TerminalSession:
    """One PTY shell scoped to a workspace root."""

    def __init__(self, workspace_root: str, shell: Optional[str] = None) -> None:
        self.id = uuid.uuid4().hex
        self.workspace_root = workspace_root
        self.workspace_id: Optional[str] = None  # set by the manager
        self.created_at = None  # set by the manager
        self.pid: Optional[int] = None
        self.master_fd: Optional[int] = None
        self._output: Queue = Queue()
        self._closed = False
        self._lock = threading.Lock()
        self.pending_confirmation: Optional[str] = None  # destructive command awaiting confirm
        self.pending_reason: Optional[str] = None
        self._reader_thread: Optional[threading.Thread] = None

        os.makedirs(workspace_root, exist_ok=True)
        argv = (shell or os.getenv("SHELL") or "/bin/sh").split()
        if not argv:
            argv = ["/bin/sh"]
        shell_path = argv[0]
        if not os.path.exists(shell_path):
            shell_path = "/bin/sh"
            argv = ["/bin/sh"]

        try:
            pid, master_fd = pty.fork()
        except OSError as e:  # pragma: no cover - non-POSIX
            raise RuntimeError(f"PTY is not available on this platform: {e}") from e

        if pid == 0:
            # Child: pin the cwd inside the workspace sandbox root.
            try:
                os.chdir(workspace_root)
                os.environ.setdefault("TERM", "xterm-256color")
                os.environ.setdefault("PS1", "\\w $ ")
                os.execvp(shell_path, argv)  # noqa: S606 — the PTY child is the intended shell
            except Exception:  # noqa: BLE001 — child must die rather than corrupt the parent
                os._exit(127)  # noqa: SLF001

        self.pid = pid
        self.master_fd = master_fd
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True, name=f"pty-{self.id}")
        self._reader_thread.start()

    # -- lifecycle ---------------------------------------------------------

    def _read_loop(self) -> None:
        """Continuously drain the PTY master into the output queue."""
        while not self._closed:
            try:
                rlist, _, _ = select.select([self.master_fd], [], [], 0.25)
            except (OSError, ValueError):
                break
            if not rlist:
                continue
            try:
                data = os.read(self.master_fd, 65536)
            except OSError as e:
                if e.errno in (errno.EIO, errno.EBADF):  # child exited / fd closed
                    self._closed = True
                break
            if not data:  # EOF — child exited
                self._closed = True
                break
            self._output.put(data)

    def write(self, data: str) -> None:
        """Write raw bytes to the PTY master (no guard — used after confirmation)."""
        if self.master_fd is None or self._closed:
            raise RuntimeError("Session is closed")
        with self._lock:
            os.write(self.master_fd, data.encode("utf-8", errors="replace"))

    def submit_input(self, data: str) -> dict:
        """
        Submit input through the destructive-command guard (Phase 5.1).

        Returns ``{"blocked": False}`` on success, or
        ``{"blocked": True, "command": ..., "reason": ...}`` when the input
        matches a destructive pattern and needs explicit confirmation. The
        exact same input must be resubmitted (``confirm=True``) to run.
        """
        if self._closed:
            return {"blocked": True, "reason": "Session is closed", "command": data}

        with self._lock:
            if self.pending_confirmation is not None:
                if data.strip() == self.pending_confirmation.strip():
                    command = self.pending_confirmation
                    self.pending_confirmation = None
                    self.pending_reason = None
                    try:
                        os.write(self.master_fd, command.encode("utf-8", errors="replace"))
                    except OSError:
                        return {"blocked": True, "reason": "Session is closed", "command": command}
                    return {"blocked": False, "confirmed": True}
                return {
                    "blocked": True,
                    "command": self.pending_confirmation,
                    "reason": self.pending_reason or "destructive command",
                }

            reason = is_destructive_command(data)
            if reason:
                self.pending_confirmation = data
                self.pending_reason = reason
                return {"blocked": True, "command": data, "reason": reason}
            try:
                os.write(self.master_fd, data.encode("utf-8", errors="replace"))
            except OSError:
                return {"blocked": True, "reason": "Session is closed", "command": data}
            return {"blocked": False}

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY window (cols x rows)."""
        if self.master_fd is None or self._closed:
            return
        if fcntl is None:  # pragma: no cover - non-POSIX
            return
        winsize = struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0)
        try:
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:  # pragma: no cover - child may have exited
            pass

    def read_output(self, timeout: float = 0.1) -> bytes:
        """Drain buffered output (non-blocking; waits up to ``timeout``)."""
        chunks = bytearray()
        try:
            while True:
                chunks.extend(self._output.get_nowait())
                if len(chunks) >= _MAX_OUTPUT_BYTES:
                    break
        except Empty:
            pass
        if not chunks and not self._closed:
            try:
                chunk = self._output.get(timeout=timeout)
                chunks.extend(chunk)
            except Empty:
                pass
        return bytes(chunks)

    def close(self) -> None:
        """Kill the shell and its process group, then close the master fd."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        if self.pid:
            try:
                os.killpg(os.getpgid(self.pid), signal.SIGHUP)
                os.killpg(os.getpgid(self.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    os.kill(self.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
        if self._reader_thread:
            self._reader_thread.join(timeout=1.0)

    @property
    def alive(self) -> bool:
        return not self._closed and self.master_fd is not None


class TerminalManager:
    """Registry of terminal sessions, keyed by id, scoped by workspace."""

    def __init__(self) -> None:
        self._sessions: Dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def create(self, workspace_id: str, workspace_root: str, cwd: Optional[str] = None, shell: Optional[str] = None) -> TerminalSession:
        """Create a session whose cwd is pinned inside ``workspace_root``."""
        from datetime import datetime, timezone

        root = os.path.realpath(workspace_root)
        if cwd:
            candidate = os.path.realpath(os.path.join(root, cwd))
            if os.path.commonpath([root, candidate]) != root:
                raise ValueError(f"cwd must stay inside the workspace root: {cwd}")
            root = candidate
        session = TerminalSession(root, shell=shell)
        session.workspace_id = workspace_id
        session.created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._sessions[session.id] = session
        logger.info("Terminal session created", session=session.id, workspace_root=root)
        return session

    def get(self, session_id: str) -> Optional[TerminalSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def list_for_workspace(self, workspace_id: str) -> List[TerminalSession]:
        with self._lock:
            return [s for s in self._sessions.values() if getattr(s, "workspace_id", None) == workspace_id]

    def close(self, session_id: str) -> bool:
        """Close and drop a session (kill-on-disconnect)."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.close()
        return True

    def close_all_for_workspace(self, workspace_id: str) -> int:
        count = 0
        for session in self.list_for_workspace(workspace_id):
            if self.close(session.id):
                count += 1
        return count


# Module-level singleton used by the platform API.
_manager = TerminalManager()


def get_terminal_manager() -> TerminalManager:
    return _manager
