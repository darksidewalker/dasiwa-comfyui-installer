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
