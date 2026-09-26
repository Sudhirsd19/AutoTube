"""Terminal output styling using Rich, robust across Windows encodings."""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

custom_theme = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "highlight": "bold magenta",
        "dim": "dim white",
    }
)

console = Console(theme=custom_theme, highlight=False)


def print_banner():
    banner = """
=================================================================
                     >>   A U T O T U B E   <<
   End-to-End AI YouTube Shorts, Long-form & Auto-Uploader
=================================================================
"""
    console.print(banner, style="bold cyan")


def print_step(step_number: int, total_steps: int, title: str):
    console.print(
        f"\n[bold cyan]--- Step {step_number}/{total_steps}: [bold white]{title}[/bold white] ---[/bold cyan]"
    )


def print_success(message: str):
    console.print(f" [success][OK][/success] {message}")


def print_info(message: str):
    console.print(f" [info][*][/info] {message}")


def print_warning(message: str):
    console.print(f" [warning][!][/warning] {message}")


def print_error(message: str):
    console.print(f" [error][X][/error] {message}")


def print_panel(content: str, title: str = "", border_style: str = "cyan"):
    console.print(Panel(content, title=title, border_style=border_style))
