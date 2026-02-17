import os
import sys

class Logger:
    # ANSI Colors
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

    @staticmethod
    def init():
        """Enable ANSI support for Windows terminals."""
        if os.name == 'nt':
            os.system('color')

    @classmethod
    def log(cls, text, level="info", bold=False):
        style = cls.BOLD if bold else ""
        
        # Mapping levels to prefixes and colors
        formats = {
            "info":  (cls.CYAN, "[*]"),
            "ok":    (cls.GREEN, "[+]"),
            "warn":  (cls.YELLOW, "[!]"),
            "fail":  (cls.RED, "[-]"),
            "start": (cls.CYAN, "[START]"),
            "done":  (cls.GREEN, "[DONE]")
        }
        
        color, prefix = formats.get(level, (cls.CYAN, "[*]"))
        
        # Construct message
        message = f"{style}{color}{prefix} {text}{cls.END}"
        print(message, flush=True)

    @classmethod
    def error(cls, text):
        cls.log(text, "fail", bold=True)

    @classmethod
    def success(cls, text):
        cls.log(text, "done")
