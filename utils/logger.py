import os
import sys
import time
import threading
import itertools
from contextlib import contextmanager


class Logger:
    # ANSI Colors
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'

    _ansi_enabled = True

    @staticmethod
    def init():
        """Enable ANSI support for Windows terminals (Win 10+ supports VT sequences)."""
        if os.name == 'nt':
            # Try to enable virtual terminal processing
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            except Exception:
                # Fallback: `color` command toggles ANSI on older cmd.exe
                os.system('color')

        # Respect NO_COLOR convention
        if os.environ.get("NO_COLOR"):
            Logger._ansi_enabled = False
            for attr in ("GREEN", "CYAN", "YELLOW", "RED", "MAGENTA",
                        "BLUE", "GRAY", "BOLD", "DIM", "END"):
                setattr(Logger, attr, "")

    # ---------- Core logging ----------

    @classmethod
    def log(cls, text, level="info", bold=False):
        style = cls.BOLD if bold else ""
        formats = {
            "info":    (cls.CYAN,    "[*]"),
            "ok":      (cls.GREEN,   "[+]"),
            "warn":    (cls.YELLOW,  "[!]"),
            "fail":    (cls.RED,     "[-]"),
            "error":   (cls.RED,     "[-]"),
            "start":   (cls.CYAN,    "[START]"),
            "done":    (cls.GREEN,   "[DONE]"),
            "magenta": (cls.MAGENTA, "[*]"),
            "debug":   (cls.GRAY,    "[.]"),
        }
        color, prefix = formats.get(level, (cls.CYAN, "[*]"))
        print(f"{style}{color}{prefix} {text}{cls.END}", flush=True)

    @classmethod
    def error(cls, text):
        cls.log(text, "fail", bold=True)

    @classmethod
    def success(cls, text):
        cls.log(text, "done")

    @classmethod
    def warn(cls, text):
        cls.log(text, "warn")

    @classmethod
    def info(cls, text):
        cls.log(text, "info")

    @classmethod
    def debug(cls, text):
        cls.log(text, "debug")

    # ---------- Framing / banners ----------

    @classmethod
    def banner(cls, title, subtitle=None, width=62):
        """A double-lined box for big section breaks."""
        print()
        top    = "╔" + "═" * (width - 2) + "╗"
        bottom = "╚" + "═" * (width - 2) + "╝"
        mid    = "║" + " " * (width - 2) + "║"
        title_line = f"║{title.center(width - 2)}║"
        print(f"{cls.BOLD}{cls.CYAN}{top}{cls.END}")
        print(f"{cls.BOLD}{cls.CYAN}{title_line}{cls.END}")
        if subtitle:
            sub_line = f"║{subtitle.center(width - 2)}║"
            print(f"{cls.CYAN}{sub_line}{cls.END}")
        print(f"{cls.BOLD}{cls.CYAN}{bottom}{cls.END}")
        print()

    @classmethod
    def section(cls, title, width=62):
        """A single-lined header for regular phases."""
        print()
        line = "─" * width
        pad  = max(2, (width - len(title) - 2) // 2)
        header = "─" * pad + f" {title} " + "─" * (width - pad - len(title) - 2)
        print(f"{cls.BOLD}{cls.CYAN}{line}{cls.END}")
        print(f"{cls.BOLD}{cls.CYAN}{header}{cls.END}")
        print(f"{cls.BOLD}{cls.CYAN}{line}{cls.END}")

    @classmethod
    def rule(cls, width=62):
        print(f"{cls.GRAY}{'─' * width}{cls.END}")

    @classmethod
    def kv(cls, key, value, width=18):
        """Aligned key/value pair for summaries."""
        print(f"  {cls.CYAN}{cls.BOLD}{key:<{width}}{cls.END} {value}")

    # ---------- Prompts ----------

    @classmethod
    def ask(cls, question, default=None):
        """Plain text question with optional default."""
        suffix = f" {cls.DIM}[{default}]{cls.END}" if default else ""
        try:
            response = input(f"{cls.CYAN}{cls.BOLD}?{cls.END} {question}{suffix}: ").strip()
        except EOFError:
            return default or ""
        return response if response else (default or "")

    @classmethod
    def ask_yes_no(cls, question, default=True):
        """Y/N prompt that returns a bool. Accepts y, yes, n, no, or empty -> default."""
        indicator = "[Y/n]" if default else "[y/N]"
        while True:
            try:
                response = input(f"{cls.CYAN}{cls.BOLD}?{cls.END} {question} "
                                 f"{cls.DIM}{indicator}{cls.END}: ").strip().lower()
            except EOFError:
                return default
            if not response:
                return default
            if response in ("y", "yes"):
                return True
            if response in ("n", "no"):
                return False
            cls.warn("Please answer y or n.")

    @classmethod
    def ask_choice(cls, question, options, default_index=0):
        """Numbered menu. options = list of (label, description_or_None).
        Returns the chosen index."""
        print()
        print(f"{cls.CYAN}{cls.BOLD}? {question}{cls.END}")
        for i, opt in enumerate(options, 1):
            label, desc = (opt if isinstance(opt, tuple) else (opt, None))
            marker = f"{cls.GREEN}●{cls.END}" if (i - 1) == default_index else f"{cls.GRAY}○{cls.END}"
            line = f"  {marker} {cls.BOLD}{i}.{cls.END} {label}"
            if desc:
                line += f"  {cls.DIM}— {desc}{cls.END}"
            print(line)
        while True:
            try:
                raw = input(f"\n{cls.CYAN}Select [1-{len(options)}] "
                            f"{cls.DIM}(default: {default_index + 1}){cls.END}: ").strip()
            except EOFError:
                return default_index
            if not raw:
                return default_index
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return idx
            except ValueError:
                pass
            cls.warn(f"Enter a number between 1 and {len(options)}.")

    # ---------- Single-key reader (cross-platform) ----------

    @classmethod
    @contextmanager
    def _raw_terminal(cls):
        """
        Put the controlling terminal into a mode suitable for single-key reads
        for the duration of the with-block. No-op on Windows (msvcrt does not
        require mode changes). Yields True on success, False if unavailable.
        """
        if os.name == 'nt':
            yield True
            return
        try:
            import termios, tty
        except ImportError:
            yield False
            return
        if not sys.stdin.isatty():
            yield False
            return
        fd = sys.stdin.fileno()
        try:
            old = termios.tcgetattr(fd)
        except termios.error:
            yield False
            return
        try:
            tty.setcbreak(fd)
            yield True
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    @classmethod
    def _read_key(cls):
        """
        Read a single keypress. Must be called inside `with cls._raw_terminal()`
        on POSIX, or any time on Windows. Returns one of:
          'up', 'down', 'space', 'enter', 'a', 'n', 'q', 'abort', or a raw char.
        Returns None if reading is not possible.
        """
        if os.name == 'nt':
            try:
                import msvcrt
            except ImportError:
                return None
            ch = msvcrt.getwch()
            # Arrow keys / function keys send a prefix (\x00 or \xe0) then a code
            if ch in ('\x00', '\xe0'):
                code = msvcrt.getwch()
                if code == 'H': return 'up'
                if code == 'P': return 'down'
                return ''
            if ch in ('\r', '\n'): return 'enter'
            if ch == ' ': return 'space'
            if ch == '\x03': return 'abort'      # Ctrl-C
            if ch == '\x1b': return 'q'          # Esc
            return ch.lower()

        # POSIX (terminal already in cbreak mode via _raw_terminal).
        # We use os.read on the raw fd rather than sys.stdin.read to avoid
        # Python's input buffering hiding pending bytes from select().
        try:
            import select as _select
        except ImportError:
            return None
        fd = sys.stdin.fileno()
        try:
            data = os.read(fd, 1)
        except (OSError, ValueError):
            return None
        if not data:
            return None
        ch = data.decode('utf-8', errors='replace')
        if ch == '\x1b':
            # Could be Esc alone or start of escape sequence (arrow keys).
            # Wait briefly for the rest of the sequence.
            rlist, _, _ = _select.select([fd], [], [], 0.1)
            if not rlist:
                return 'q'
            try:
                seq = os.read(fd, 2).decode('utf-8', errors='replace')
            except (OSError, ValueError):
                return 'q'
            if seq == '[A': return 'up'
            if seq == '[B': return 'down'
            return ''
        if ch in ('\r', '\n'): return 'enter'
        if ch == ' ': return 'space'
        if ch == '\x03': return 'abort'      # Ctrl-C
        if ch == '\x04': return 'q'          # Ctrl-D
        return ch.lower()

    # ---------- Multi-select prompt ----------

    @classmethod
    def ask_multiselect(cls, question, options, hint=None):
        """
        Multi-select picker. options = list of (label, description_or_None) or list of str.
        Returns a list of selected indices (possibly empty).

        Interactive mode (TTY + ANSI):
          up/down navigate, Space toggle, 'a' all, 'n' none, Enter confirm, Esc/q cancel.

        Fallback mode (non-TTY, no ANSI, or key reading unavailable):
          Numbered list with comma-separated input. 'all', 'none' (default), or e.g. '1,3,5'.
        """
        # Normalise to (label, desc) tuples
        norm = [(o if isinstance(o, tuple) else (o, None)) for o in options]
        n = len(norm)
        if n == 0:
            return []

        interactive = (
            cls._ansi_enabled
            and sys.stdout.isatty()
            and sys.stdin.isatty()
            and os.name in ('nt', 'posix')
        )

        if interactive:
            result = cls._multiselect_interactive(question, norm, hint)
            if result is not None:
                return result
            # Interactive failed (e.g. termios unavailable) — fall through to text mode

        return cls._multiselect_fallback(question, norm, hint)

    @classmethod
    def _multiselect_interactive(cls, question, norm, hint):
        n = len(norm)
        selected = [False] * n
        cursor = 0

        print()
        print(f"{cls.CYAN}{cls.BOLD}? {question}{cls.END}")
        hint_line = hint or ("up/down move  ·  Space toggle  ·  'a' all  ·  "
                             "'n' none  ·  Enter confirm  ·  Esc cancel")
        print(f"  {cls.DIM}{hint_line}{cls.END}")

        # Reserve lines for the option list
        for _ in range(n):
            print("")

        sys.stdout.write("\033[?25l")  # hide cursor
        sys.stdout.flush()

        try:
            with cls._raw_terminal() as raw_ok:
                if not raw_ok:
                    # Raw mode setup failed — fall back to text mode
                    return None
                while True:
                    # Move back to start of list and redraw
                    sys.stdout.write(f"\033[{n}A")
                    for i, (label, desc) in enumerate(norm):
                        box = (f"{cls.GREEN}[x]{cls.END}" if selected[i]
                               else f"{cls.GRAY}[ ]{cls.END}")
                        if i == cursor:
                            arrow = f"{cls.CYAN}{cls.BOLD}>{cls.END}"
                            text = f"{cls.BOLD}{label}{cls.END}"
                        else:
                            arrow = " "
                            text = f"{cls.GRAY}{label}{cls.END}"
                        line = f" {arrow} {box} {text}"
                        if desc:
                            line += f"  {cls.DIM}— {desc}{cls.END}"
                        sys.stdout.write(f"\r\033[K{line}\n")
                    sys.stdout.flush()

                    key = cls._read_key()
                    if key is None:
                        return None
                    if key == 'up':
                        cursor = (cursor - 1) % n
                    elif key == 'down':
                        cursor = (cursor + 1) % n
                    elif key == 'space':
                        selected[cursor] = not selected[cursor]
                    elif key == 'a':
                        all_on = all(selected)
                        selected = [not all_on] * n
                    elif key == 'n':
                        selected = [False] * n
                    elif key == 'enter':
                        return [i for i, s in enumerate(selected) if s]
                    elif key == 'q':
                        return []
                    elif key == 'abort':
                        raise KeyboardInterrupt()
        finally:
            sys.stdout.write("\033[?25h")  # show cursor
            sys.stdout.flush()

    @classmethod
    def _multiselect_fallback(cls, question, norm, hint):
        print()
        print(f"{cls.CYAN}{cls.BOLD}? {question}{cls.END}")
        for i, (label, desc) in enumerate(norm, 1):
            line = f"  {cls.DIM}{i}.{cls.END} {label}"
            if desc:
                line += f"  {cls.DIM}— {desc}{cls.END}"
            print(line)
        print(f"\n  {cls.DIM}Enter numbers (e.g. 1,3), 'all', or "
              f"'none' (default) to skip{cls.END}")
        try:
            raw = input(f"{cls.CYAN}{cls.BOLD}?{cls.END} Selection "
                        f"{cls.DIM}[none]{cls.END}: ").strip()
        except EOFError:
            return []
        low = raw.lower()
        if low in ("", "none", "skip", "n"):
            return []
        if low == "all":
            return list(range(len(norm)))
        try:
            indices = [int(x) - 1 for x in raw.replace(',', ' ').split()]
        except ValueError:
            cls.warn("Unrecognised selection — skipping.")
            return []
        return [i for i in indices if 0 <= i < len(norm)]

    # ---------- Spinner for long ops ----------

    @classmethod
    @contextmanager
    def spinner(cls, message):
        """Use as: with Logger.spinner('Doing thing'): ... ."""
        if not cls._ansi_enabled or not sys.stdout.isatty():
            cls.info(message + " ...")
            start = time.time()
            try:
                yield
                cls.success(f"{message} ({time.time() - start:.1f}s)")
            except Exception:
                cls.error(f"{message} failed")
                raise
            return

        frames = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        stop = threading.Event()
        start = time.time()

        def spin():
            while not stop.is_set():
                frame = next(frames)
                sys.stdout.write(
                    f"\r{cls.CYAN}{frame}{cls.END} {message} "
                    f"{cls.DIM}({time.time() - start:.1f}s){cls.END}   "
                )
                sys.stdout.flush()
                time.sleep(0.1)

        t = threading.Thread(target=spin, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()
            t.join(timeout=0.5)
            sys.stdout.write("\r" + " " * (len(message) + 30) + "\r")
            sys.stdout.flush()
        cls.success(f"{message} ({time.time() - start:.1f}s)")
