# Yank : YouTube Downloader for Linux

## Overview

**Yank** is a small, fast, and reliable desktop application for downloading YouTube videos and audio on Linux. It is a thin graphical wrapper around the battle-tested `yt-dlp` engine and `ffmpeg`, packaged as a single Python file that runs on Tkinter  the GUI toolkit already shipped with most Linux distributions.

Yank was built with one idea in mind: **do one job, do it well, and stay out of the way.** There is no Electron, no webview, no bundled runtime, no background service, and no account, telemetry, or cloud dependency. You paste a URL, choose what you want, and press Download. That is the entire experience.

---

## Why Yank Exists

Most YouTube downloaders for Linux fall into one of two camps:

1. **Heavy graphical suites** that bundle hundreds of megabytes of dependencies for what is, at its core, a single command-line call.
2. **Raw CLI tools** that are powerful but require memorizing flags, format codes, and post-processing options.

Yank occupies the space in between: a **minimal GUI** that exposes only the decisions a normal user actually needs to make  video or audio, which quality, and where to save it  while delegating all the hard work to `yt-dlp`, the most actively maintained and stable downloader in existence.

---

## Key Features

- **Video downloads (MP4)**  Automatically selects the best available video and audio streams and merges them into a single MP4 file using `ffmpeg`.
- **Audio-only downloads (MP3)**  Extracts and converts audio to MP3 with a selectable bitrate (Best, 320, 192, or 128 kbps).
- **Quality control**  Choose Best available, 1080p, 720p, or 480p for video, with graceful fallback when a requested resolution is unavailable.
- **Output folder picker**  Pick any folder; Yank remembers your last choice between launches.
- **Live progress and logs**  A progress bar and a scrollable log area show exactly what `yt-dlp` is doing, including errors and completion messages.
- **Safe cancellation**  The Cancel button terminates the download cleanly without leaving partial processes behind.
- **Dependency checks**  On startup, Yank verifies that `yt-dlp` and `ffmpeg` are installed and shows a clear, actionable message if they are not.
- **Persistent configuration**  A small JSON file in `~/.config/yank/` stores your last output folder and preferences.
- **Non-blocking UI**  Downloads run in a background thread, so the window never freezes, even during long downloads or network stalls.

---

## Design Philosophy

Yank follows four principles:

1. **Lightweight.** A single Python file using only the standard library. No pip packages, no virtualenv, no compilation step.
2. **Fast.** Startup is near-instant. The app does not load a browser engine or a large framework  it opens a window and waits for input.
3. **Stable.** All downloading is handled by `yt-dlp`, which is updated frequently to keep pace with YouTube's changes. Yank itself has almost no moving parts, so there is little that can break.
4. **Easy to use.** Four controls: URL, mode, quality, folder. A first-time user can complete a download in under ten seconds.

---

## How It Works

Yank does not reimplement any downloading logic. It builds a `yt-dlp` command based on your selections and runs it as a subprocess, streaming its output back to the GUI in real time.

- For **video mode**, it calls `yt-dlp` with a format expression that requests the best MP4 video and M4A audio, then merges them with `ffmpeg`.
- For **audio mode**, it uses `yt-dlp`'s `-x` flag with `--audio-format mp3` and the chosen bitrate.
- The output template saves files as `<video title>.<ext>` inside the folder you selected.

Because the app calls the same commands you would type in a terminal, anything `yt-dlp` can do  age-restricted videos, playlists, subtitles, metadata embedding, retries on network failure  remains available and can be enabled later by editing the generated command or extending the config.

---

## System Requirements

- **OS:** Any modern Linux distribution (tested on Debian/Ubuntu, Arch, and Fedora).
- **Python:** 3.10 or newer, with Tkinter (included in standard Python installs on most distributions; may require `python3-tk` on some Debian-based systems).
- **External tools:** `yt-dlp` and `ffmpeg`.
- **Optional:** A JavaScript runtime such as Deno or Node.js 22+ for full format support on some YouTube videos.

**Install dependencies:**

```bash
# Debian / Ubuntu
sudo apt install python3-tk ffmpeg
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

# Arch Linux
sudo pacman -S python tk ffmpeg yt-dlp

# Optional: Deno JavaScript runtime (recommended for newer YouTube format handling)
sudo pacman -S deno

# Fedora
sudo dnf install python3-tkinter ffmpeg yt-dlp deno
```

---

## Running Yank

Open a terminal in the repository directory and run:

```bash
cd /workspaces/yank
python3 ./yank.py
```

Yank must run in a graphical Linux desktop session. It does not run from a headless
terminal or SSH session unless that session has a configured display.

For a desktop launcher or shell shortcut, make the script executable:

```bash
chmod +x ./yank.py
./yank.py
```

You can also create a shell alias:

```bash
alias yank='python3 /workspaces/yank/yank.py'
```

---

## Typical Workflow

1. Copy a YouTube URL.
2. Open Yank and paste it into the URL field.
3. Choose **Video MP4** or **Audio MP3**.
4. Pick a quality.
5. Select an output folder (remembered for next time).
6. Click **Download**.
7. Watch the progress bar and log; the file appears in your chosen folder when finished.

That is the whole application.

---

## Limitations

Yank is intentionally simple. It does **not** currently support playlists, batch downloads, channel subscriptions, subtitles, thumbnail embedding, or download scheduling. These are all things `yt-dlp` can do, and they may be added in future versions  but the goal is to keep the interface small, so any additions will be opt-in and unobtrusive.

---

## Summary

Yank is a small, honest tool for a common task. It respects your system resources, your time, and your intelligence. It does not try to be a media manager, a browser extension, or a platform. It is a button that downloads what you paste into it  built the Linux way: **minimal, transparent, and dependable.**

If you already trust `yt-dlp`, Yank is simply a friendlier face for it.
