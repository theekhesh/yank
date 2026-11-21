#!/usr/bin/env python3
"""A lightweight Tkinter GUI for downloading YouTube media with yt-dlp."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse


CONFIG_DIR = Path.home() / ".config" / "yank"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_OUTPUT = Path.home() / "Downloads"


class YankApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube Downloader")
        self.geometry("760x560")
        self.minsize(680, 500)

        self.download_thread: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.cancel_requested = False
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()

        config = self.load_config()
        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="video")
        self.quality_var = tk.StringVar(value="Best available")
        self.output_var = tk.StringVar(
            value=str(self._output_from_config(config))
        )
        self.ytdlp_var = tk.StringVar(
            value=str(config.get("yt_dlp_path", "") or "")
        )
        theme = str(config.get("theme", "light")).lower()
        self.theme_var = tk.StringVar(
            value="Dark" if theme == "dark" else "Light"
        )

        self._build_ui()
        self._apply_theme()
        self._check_dependencies()
        self.after(80, self._poll_messages)

    def _build_ui(self) -> None:
        padding = {"padx": 12, "pady": 6}
        outer = ttk.Frame(self, style="App.TFrame")
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="Header.TFrame")
        header.pack(fill="x", padx=12, pady=(12, 8))
        ttk.Label(
            header,
            text="Yank",
            style="Title.TLabel",
        ).pack(side="left")
        ttk.Label(header, text="YouTube Downloader", style="Subtitle.TLabel").pack(
            side="left", padx=(10, 0), pady=(4, 0)
        )
        ttk.Label(header, text="Theme", style="Field.TLabel").pack(
            side="right", padx=(8, 5)
        )
        theme = ttk.Combobox(
            header,
            textvariable=self.theme_var,
            values=["Light", "Dark"],
            state="readonly",
            width=8,
        )
        theme.pack(side="right")
        theme.bind("<<ComboboxSelected>>", lambda _event: self._change_theme())

        card = ttk.Frame(outer, style="Card.TFrame")
        card.pack(fill="x", padx=12, pady=(0, 8))

        url_frame = ttk.Frame(card, style="Card.TFrame")
        url_frame.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(url_frame, text="YouTube URL", style="Field.TLabel").pack(
            anchor="w"
        )
        ttk.Entry(url_frame, textvariable=self.url_var).pack(
            fill="x", pady=(4, 0)
        )

        options = ttk.Frame(card, style="Card.TFrame")
        options.pack(fill="x", padx=12, pady=6)
        left = ttk.Frame(options, style="Card.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="Download type", style="Field.TLabel").pack(anchor="w")
        mode = ttk.Frame(left, style="Card.TFrame")
        mode.pack(fill="x", pady=(4, 0))
        ttk.Radiobutton(
            mode, text="Video MP4", variable=self.mode_var, value="video",
            command=self._update_quality_choices,
        ).pack(side="left")
        ttk.Radiobutton(
            mode, text="Audio MP3", variable=self.mode_var, value="audio",
            command=self._update_quality_choices,
        ).pack(side="left", padx=(12, 0))

        right = ttk.Frame(options, style="Card.TFrame")
        right.pack(side="right", padx=(12, 0))
        ttk.Label(right, text="Quality", style="Field.TLabel").pack(anchor="w")
        self.quality_combo = ttk.Combobox(
            right, textvariable=self.quality_var, state="readonly", width=20
        )
        self.quality_combo.pack(pady=(4, 0))
        self._update_quality_choices()

        self._add_path_row(
            card, "Output folder", self.output_var, self._browse_folder
        )
        self._add_path_row(
            card, "yt-dlp path (optional)", self.ytdlp_var,
            self._browse_ytdlp
        )

        action_frame = ttk.Frame(card, style="Card.TFrame")
        action_frame.pack(fill="x", padx=12, pady=(6, 12))
        self.download_button = ttk.Button(
            action_frame, text="Download", style="Accent.TButton",
            command=self._start_download
        )
        self.download_button.pack(side="left")
        self.cancel_button = ttk.Button(
            action_frame,
            text="Cancel",
            command=self._cancel_download,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(5, 0))

        progress_card = ttk.Frame(outer, style="Card.TFrame")
        progress_card.pack(fill="x", padx=12, pady=(0, 8))
        progress_frame = ttk.Frame(progress_card, style="Card.TFrame")
        progress_frame.pack(fill="x", padx=10, pady=(5, 0))
        self.progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x")

        status_frame = ttk.Frame(progress_card, style="Card.TFrame")
        status_frame.pack(fill="x", padx=10, pady=(2, 5))
        ttk.Label(status_frame, text="Status:", style="Field.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            style="Status.TLabel",
        ).pack(
            side="left",
            padx=(5, 0),
        )

        log_frame = ttk.LabelFrame(
            outer, text="Activity log", style="Log.TLabelframe"
        )
        log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log = tk.Text(log_frame, wrap="word", height=10)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set, state="disabled")

    def _add_path_row(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        browse_command,
    ) -> None:
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", padx=12, pady=6)
        ttk.Label(row, text=label, style="Field.TLabel").pack(anchor="w")
        controls = ttk.Frame(row, style="Card.TFrame")
        controls.pack(fill="x", pady=(4, 0))
        ttk.Entry(controls, textvariable=variable).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(controls, text="Browse...", command=browse_command).pack(
            side="left", padx=(6, 0)
        )

    def load_config(self) -> dict:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _output_from_config(self, config: dict) -> Path:
        saved = config.get("output_folder")
        if isinstance(saved, str):
            folder = Path(saved).expanduser()
            if folder.is_dir():
                return folder

        if DEFAULT_OUTPUT.is_dir():
            return DEFAULT_OUTPUT
        return Path.home()

    def save_output_folder(self, folder: Path) -> None:
        self.save_config({"output_folder": str(folder)})

    def save_config(self, updates: dict) -> None:
        try:
            config = self.load_config()
            config.update(updates)
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json.dumps(config, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            self._append_log(f"Could not save settings: {exc}\n")

    def _update_quality_choices(self) -> None:
        if self.mode_var.get() == "video":
            choices = [
                "Best available", "1080p", "720p", "480p", "360p", "240p"
            ]
        else:
            choices = ["Best MP3", "320 kbps", "192 kbps", "128 kbps"]
        self.quality_combo.configure(values=choices)
        if self.quality_var.get() not in choices:
            self.quality_var.set(choices[0])

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(
            initialdir=self.output_var.get() or str(Path.home()),
            title="Select output folder",
        )
        if folder:
            self.output_var.set(folder)

    def _browse_ytdlp(self) -> None:
        initial = self.ytdlp_var.get().strip()
        initial_dir = str(Path(initial).expanduser().parent) if initial else str(Path.home())
        executable = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Select yt-dlp executable",
        )
        if executable:
            self.ytdlp_var.set(executable)
            self.save_config({"yt_dlp_path": executable})
            self._check_dependencies()

    def _change_theme(self) -> None:
        theme = self.theme_var.get().lower()
        self.save_config({"theme": theme})
        self._apply_theme()

    def _apply_theme(self) -> None:
        theme_name = self.theme_var.get().lower()
        if theme_name not in ("light", "dark"):
            theme_name = "light"
            self.theme_var.set("Light")

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        if theme_name == "dark":
            colors = {
                "bg": "#17191c", "card": "#23262b", "field": "#1c1f23",
                "text": "#f4f5f7", "muted": "#a9afb8", "border": "#3a3f46",
                "accent": "#6c8cff", "accent_hover": "#7c99ff",
                "input": "#2a2e34", "log": "#111316",
            }
        else:
            colors = {
                "bg": "#f3f5f8", "card": "#ffffff", "field": "#ffffff",
                "text": "#20242a", "muted": "#657080", "border": "#d8dde5",
                "accent": "#4f66d9", "accent_hover": "#3f55c3",
                "input": "#ffffff", "log": "#fafbfc",
            }

        self.configure(background=colors["bg"])
        style.configure(".", background=colors["bg"], foreground=colors["text"])
        style.configure("App.TFrame", background=colors["bg"])
        style.configure("Header.TFrame", background=colors["bg"])
        style.configure("Card.TFrame", background=colors["card"])
        style.configure("Title.TLabel", background=colors["bg"], foreground=colors["text"],
                        font=("TkDefaultFont", 20, "bold"))
        style.configure("Subtitle.TLabel", background=colors["bg"], foreground=colors["muted"],
                        font=("TkDefaultFont", 10))
        style.configure("Field.TLabel", background=colors["card"], foreground=colors["muted"],
                        font=("TkDefaultFont", 9, "bold"))
        style.configure("Status.TLabel", background=colors["card"], foreground=colors["text"])
        style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
        style.configure("TEntry", fieldbackground=colors["input"], foreground=colors["text"],
                        bordercolor=colors["border"], lightcolor=colors["border"],
                        darkcolor=colors["border"], padding=7)
        style.configure("TCombobox", fieldbackground=colors["input"], foreground=colors["text"],
                        bordercolor=colors["border"], lightcolor=colors["border"],
                        darkcolor=colors["border"], padding=5)
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", colors["input"]),
                ("active", colors["input"]),
                ("disabled", colors["border"]),
            ],
            foreground=[
                ("readonly", colors["text"]),
                ("disabled", colors["muted"]),
            ],
            selectbackground=[("readonly", colors["accent"])],
            selectforeground=[("readonly", "#ffffff")],
        )
        style.configure("TScrollbar",
                        background=colors["border"],
                        troughcolor=colors["card"],
                        bordercolor=colors["border"],
                        arrowcolor=colors["text"])
        style.map("TScrollbar",
                  background=[("active", colors["muted"]),
                              ("pressed", colors["accent"])])
        style.configure("TRadiobutton", background=colors["card"], foreground=colors["text"])
        style.map(
            "TRadiobutton",
            background=[("active", colors["card"]), ("disabled", colors["card"])],
            foreground=[("disabled", colors["muted"])],
            indicatorbackground=[
                ("selected", colors["accent"]),
                ("!selected", colors["input"]),
            ],
            indicatorforeground=[
                ("selected", "#ffffff"),
                ("!selected", colors["text"]),
            ],
        )
        style.configure("TButton", padding=(10, 7), relief="flat")
        style.configure("Accent.TButton", background=colors["accent"], foreground="#ffffff",
                        bordercolor=colors["accent"], padding=(16, 9),
                        font=("TkDefaultFont", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("active", colors["accent_hover"]), ("disabled", colors["border"])])
        style.configure("TProgressbar", thickness=8, troughcolor=colors["border"],
                        background=colors["accent"], bordercolor=colors["border"])
        style.configure("Log.TLabelframe", background=colors["card"], foreground=colors["text"],
                        bordercolor=colors["border"], relief="solid")
        style.configure("Log.TLabelframe.Label", background=colors["card"],
                        foreground=colors["muted"])

        self.log.configure(
            background=colors["log"],
            foreground=colors["text"],
            insertbackground=colors["text"],
            selectbackground=colors["accent"],
        )

    def _resolve_ytdlp(self) -> str | None:
        custom = self.ytdlp_var.get().strip()
        if custom:
            path = Path(custom).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
            return None
        return shutil.which("yt-dlp")

    def _check_dependencies(self) -> None:
        missing: list[str] = []
        if self._resolve_ytdlp() is None:
            missing.append("yt-dlp")
        if shutil.which("ffmpeg") is None:
            missing.append("ffmpeg")

        if missing:
            names = " and ".join(missing)
            message = (
                f"{names} is not installed or is not in PATH.\n"
                "Install it, or enter/browse to a separate yt-dlp executable."
            )
            self._append_log(message + "\n")
            self.status_var.set(f"Missing dependency: {names}")
            self.download_button.configure(state="disabled")
            self.after(100, lambda: messagebox.showerror("Missing dependency", message))
        else:
            self.status_var.set("Ready")
            if not hasattr(self, "download_thread") or self.download_thread is None:
                self.download_button.configure(state="normal")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _validate_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False

        hostname = (parsed.hostname or "").lower()
        return (
            hostname == "youtu.be"
            or hostname == "youtube.com"
            or hostname.endswith(".youtube.com")
            or hostname == "youtube-nocookie.com"
            or hostname.endswith(".youtube-nocookie.com")
        )

    def _validate_output_folder(self) -> Path | None:
        raw = self.output_var.get().strip()
        if not raw:
            messagebox.showerror("Invalid folder", "Choose an output folder.")
            return None

        folder = Path(raw).expanduser()
        if not folder.is_dir():
            messagebox.showerror(
                "Invalid folder", "The output folder does not exist."
            )
            return None
        if not os.access(folder, os.W_OK | os.X_OK):
            messagebox.showerror(
                "Invalid folder", "The output folder is not writable."
            )
            return None
        return folder

    def _start_download(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Invalid URL", "Enter a YouTube URL.")
            return
        if not self._validate_url(url):
            messagebox.showerror(
                "Invalid URL",
                "Enter a valid YouTube URL (youtube.com or youtu.be).",
            )
            return

        folder = self._validate_output_folder()
        if folder is None:
            return
        ytdlp = self._resolve_ytdlp()
        if ytdlp is None:
            messagebox.showerror(
                "yt-dlp not found",
                "Enter or browse to a valid yt-dlp executable.",
            )
            return

        self.save_output_folder(folder)
        self.save_config({
            "yt_dlp_path": self.ytdlp_var.get().strip(),
            "theme": self.theme_var.get().lower(),
        })
        self.cancel_requested = False
        self.progress.configure(mode="determinate")
        self.progress["value"] = 0
        self.status_var.set("Starting...")
        self.download_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self._append_log(f"Starting download: {url}\n")

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(url, folder),
            daemon=True,
        )
        self.download_thread.start()

    def _cancel_download(self) -> None:
        if self.process is None:
            return
        self.cancel_requested = True
        self.status_var.set("Cancelling...")
        self.cancel_button.configure(state="disabled")
        try:
            if sys.platform.startswith("linux"):
                os.killpg(self.process.pid, signal.SIGTERM)
            else:
                self.process.terminate()
        except ProcessLookupError:
            pass
        except OSError as exc:
            self.messages.put(("log", f"Could not stop download: {exc}\n"))

    def _download_worker(self, url: str, folder: Path) -> None:
        command = self._build_command(url, folder)
        self.messages.put(("log", "Command: " + " ".join(command) + "\n"))

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
            )

            assert self.process.stdout is not None
            for line in iter(self.process.stdout.readline, ""):
                if not line:
                    break
                self.messages.put(("log", line))
                percent_match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
                if percent_match:
                    try:
                        percent = float(percent_match.group(1))
                        self.messages.put(("progress", max(0.0, min(100.0, percent))))
                        self.messages.put(("status", f"Downloading... {percent:.1f}%"))
                    except ValueError:
                        pass

            return_code = self.process.wait()
            if self.cancel_requested:
                self.messages.put(("status", "Download cancelled"))
                self.messages.put(("cancelled", None))
            elif return_code == 0:
                self.messages.put(("progress", 100.0))
                self.messages.put(("status", "Download complete"))
                self.messages.put(("complete", None))
            else:
                self.messages.put(
                    ("status", f"Download failed (exit code {return_code})")
                )
                self.messages.put(("failure", None))
        except FileNotFoundError:
            self.messages.put(("log", "Error: yt-dlp or ffmpeg was not found.\n"))
            self.messages.put(("status", "Download failed"))
            self.messages.put(("failure", None))
        except Exception as exc:
            self.messages.put(("log", f"Unexpected download error: {exc}\n"))
            self.messages.put(("status", "Download failed"))
            self.messages.put(("failure", None))
        finally:
            self.process = None

    def _build_command(self, url: str, folder: Path) -> list[str]:
        output_template = str(folder / "%(title)s.%(ext)s")
        ytdlp = self._resolve_ytdlp()
        try:
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.strip("/").split("/")
            if "shorts" in path_parts:
                shorts_index = path_parts.index("shorts")
                if shorts_index + 1 < len(path_parts):
                    video_id = path_parts[shorts_index + 1]
                    url = f"https://www.youtube.com/watch?v={video_id}"
        except ValueError:
            pass

        command = [
            ytdlp or "yt-dlp",
            "--newline",
            "--no-playlist",
            "-o",
            output_template,
        ]

        if self.mode_var.get() == "audio":
            quality = self.quality_var.get()
            quality_value = "0"
            if quality != "Best MP3":
                quality_value = quality.replace(" kbps", "K")

            command.extend(
                [
                    "-x",
                    "--audio-format",
                    "mp3",
                    "--audio-quality",
                    quality_value,
                ]
            )
        else:
            quality = self.quality_var.get()
            if quality == "Best available":
                format_expression = (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                    "b[ext=mp4]/bestvideo+bestaudio/best"
                )
            else:
                height = quality[:-1]
                format_expression = (
                    f"bestvideo[height<={height}][ext=mp4]+"
                    f"bestaudio[ext=m4a]/"
                    f"b[height<={height}][ext=mp4]/"
                    f"bestvideo[height<={height}]+bestaudio/"
                    f"b[height<={height}]/best"
                )
            command.extend(
                [
                    "-f",
                    format_expression,
                    "--merge-output-format",
                    "mp4",
                ]
            )

        command.append("--")
        command.append(url)
        return command

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "log":
                    self._append_log(str(value))
                elif kind == "progress":
                    self.progress["value"] = float(value)
                elif kind == "status":
                    self.status_var.set(str(value))
                elif kind in ("complete", "failure", "cancelled"):
                    self.download_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    if kind == "complete":
                        self._append_log("Download complete.\n")
                    elif kind == "cancelled":
                        self._append_log("Download cancelled.\n")
                    else:
                        self._append_log("Download failed.\n")
        except queue.Empty:
            pass
        self.after(80, self._poll_messages)


def main() -> None:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print(
            "Cannot start YouTube Downloader: no graphical display is available.",
            file=sys.stderr,
        )
        print(
            "Run it from a Linux desktop session, or set DISPLAY/WAYLAND_DISPLAY "
            "if connecting remotely.",
            file=sys.stderr,
        )
        return

    app = YankApp()
    app.mainloop()


if __name__ == "__main__":
    main()
