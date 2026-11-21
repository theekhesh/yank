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
        self.geometry("700x500")
        self.minsize(620, 420)

        self.download_thread: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.cancel_requested = False
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()

        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="video")
        self.quality_var = tk.StringVar(value="Best available")
        self.output_var = tk.StringVar(value=str(self.load_output_folder()))

        self._build_ui()
        self._check_dependencies()
        self.after(80, self._poll_messages)

    def _build_ui(self) -> None:
        padding = {"padx": 10, "pady": 5}

        url_frame = ttk.Frame(self)
        url_frame.pack(fill="x", **padding)
        ttk.Label(url_frame, text="YouTube URL:", width=14).pack(side="left")
        ttk.Entry(url_frame, textvariable=self.url_var).pack(
            side="left", fill="x", expand=True
        )

        mode_frame = ttk.Frame(self)
        mode_frame.pack(fill="x", **padding)
        ttk.Label(mode_frame, text="Download:", width=14).pack(side="left")
        ttk.Radiobutton(
            mode_frame,
            text="Video MP4",
            variable=self.mode_var,
            value="video",
            command=self._update_quality_choices,
        ).pack(side="left")
        ttk.Radiobutton(
            mode_frame,
            text="Audio MP3",
            variable=self.mode_var,
            value="audio",
            command=self._update_quality_choices,
        ).pack(side="left", padx=(15, 0))

        quality_frame = ttk.Frame(self)
        quality_frame.pack(fill="x", **padding)
        ttk.Label(quality_frame, text="Quality:", width=14).pack(side="left")
        self.quality_combo = ttk.Combobox(
            quality_frame,
            textvariable=self.quality_var,
            state="readonly",
            width=22,
        )
        self.quality_combo.pack(side="left")
        self._update_quality_choices()

        output_frame = ttk.Frame(self)
        output_frame.pack(fill="x", **padding)
        ttk.Label(output_frame, text="Output folder:", width=14).pack(side="left")
        ttk.Entry(output_frame, textvariable=self.output_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(output_frame, text="Browse...", command=self._browse_folder).pack(
            side="left", padx=(5, 0)
        )

        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", **padding)
        self.download_button = ttk.Button(
            action_frame, text="Download", command=self._start_download
        )
        self.download_button.pack(side="left")
        self.cancel_button = ttk.Button(
            action_frame,
            text="Cancel",
            command=self._cancel_download,
            state="disabled",
        )
        self.cancel_button.pack(side="left", padx=(5, 0))

        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", padx=10, pady=(5, 0))
        self.progress = ttk.Progressbar(
            progress_frame, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x")

        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=10, pady=(2, 5))
        ttk.Label(status_frame, text="Status:").pack(side="left")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).pack(
            side="left", padx=(5, 0)
        )

        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        self.log = tk.Text(log_frame, wrap="word", height=10)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set, state="disabled")

    def load_output_folder(self) -> Path:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            saved = data.get("output_folder")
            if isinstance(saved, str):
                folder = Path(saved).expanduser()
                if folder.is_dir():
                    return folder
        except (OSError, json.JSONDecodeError):
            pass

        if DEFAULT_OUTPUT.is_dir():
            return DEFAULT_OUTPUT
        return Path.home()

    def save_output_folder(self, folder: Path) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json.dumps({"output_folder": str(folder)}, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            self._append_log(f"Could not save settings: {exc}\n")

    def _update_quality_choices(self) -> None:
        if self.mode_var.get() == "video":
            choices = ["Best available", "1080p", "720p", "480p"]
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

    def _check_dependencies(self) -> None:
        missing: list[str] = []
        for executable in ("yt-dlp", "ffmpeg"):
            if shutil.which(executable) is None:
                missing.append(executable)

        if missing:
            names = " and ".join(missing)
            message = (
                f"{names} is not installed or is not in PATH.\n"
                "Install it and restart Yank."
            )
            self._append_log(message + "\n")
            self.status_var.set(f"Missing dependency: {names}")
            self.download_button.configure(state="disabled")
            self.after(100, lambda: messagebox.showerror("Missing dependency", message))

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

        self.save_output_folder(folder)
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
        command = ["yt-dlp", "--newline", "--no-playlist", "-o", output_template]

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
                format_expression = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/b[ext=mp4]/best"
            else:
                height = quality[:-1]
                format_expression = (
                    f"bestvideo[height<={height}][ext=mp4]+"
                    f"bestaudio[ext=m4a]/b[height<={height}][ext=mp4]/"
                    f"best[height<={height}]/best"
                )
            command.extend(
                [
                    "-f",
                    format_expression,
                    "--merge-output-format",
                    "mp4",
                ]
            )

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
