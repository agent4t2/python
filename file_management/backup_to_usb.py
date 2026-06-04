#!/usr/bin/env python3
"""
Portable backup script.

Enhancements in this build:
- Each source is copied under its own subfolder in the destination.
- Subfolder name is preserved exactly (including spaces) by default.
- You can override the subfolder name per source using a mapping in --sources:
- Fixed: skip-if-up-to-date logic now correctly compares source vs destination mtime.
- Built-in terminal progress bar shows byte-level copy progress.
"""

import os
import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Callable, Iterable, List, Tuple, Optional

# -------------------------
# Parsing
# -------------------------

def parse_sources_with_mapping(s: str) -> List[Tuple[Path, Optional[str]]]:
    """
    Parse comma-separated sources, where each item can be either:
      - /absolute/path
      - /absolute/path=Subfolder Name With Spaces
    Returns a list of tuples: (source_path, explicit_subfolder_name_or_None)
    """
    items = [p.strip() for p in s.split(',') if p.strip()]
    result: List[Tuple[Path, Optional[str]]] = []
    for item in items:
        if '=' in item:
            left, right = item.split('=', 1)
            src = Path(left).expanduser().resolve()
            # Preserve the subfolder name exactly as provided (including spaces)
            subfolder = right.strip()
            result.append((src, subfolder))
        else:
            src = Path(item).expanduser().resolve()
            result.append((src, None))
    return result

# -------------------------
# Helpers
# -------------------------

def notify(title: str, message: str, notifier_path: Optional[str]) -> None:
    if not notifier_path:
        return
    np = Path(notifier_path)
    if np.exists():
        try:
            subprocess.run([str(np), "-title", title, "-message", message], check=False)
        except Exception:
            pass

def log_line(logfile: Path, message: str) -> None:
    logfile.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with logfile.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")

def is_hidden(path: Path) -> bool:
    return any(part.startswith('.') for part in path.parts)

def iter_files(src_dir: Path) -> Iterable[Path]:
    for root, _, files in os.walk(src_dir):
        r = Path(root)
        if is_hidden(r):
            continue
        for name in files:
            p = r / name
            if is_hidden(p):
                continue
            yield p

def get_basename_exact(path: Path) -> str:
    # Exact final component string as seen by OS, including spaces.
    return str(path).rstrip(os.sep).split(os.sep)[-1]

def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"

class TextProgressBar:
    def __init__(self, total: int, label: str = "Copying", width: int = 36, enabled: bool = True) -> None:
        self.total = max(total, 0)
        self.label = label
        self.width = width
        self.enabled = enabled and sys.stderr.isatty()
        self.current = 0
        self._rendered = False

    def update(self, amount: int) -> None:
        if amount <= 0:
            return
        self.current = min(self.current + amount, self.total)
        self.render()

    def render(self) -> None:
        if not self.enabled:
            return

        if self.total:
            ratio = self.current / self.total
        else:
            ratio = 1.0

        filled = int(self.width * ratio)
        bar = "#" * filled + "-" * (self.width - filled)
        percent = ratio * 100
        message = (
            f"\r{self.label}: [{bar}] {percent:6.2f}% "
            f"{format_bytes(self.current)} / {format_bytes(self.total)}"
        )
        print(message, end="", file=sys.stderr, flush=True)
        self._rendered = True

    def finish(self) -> None:
        if self.total and self.current < self.total:
            self.current = self.total
            self.render()
        if self.enabled and self._rendered:
            print(file=sys.stderr)

def file_needs_copy(src: Path, dest: Path) -> bool:
    if not dest.exists():
        return True

    try:
        src_stat = src.stat()
        dst_stat = dest.stat()
        # Skip if same size and destination is newer or same mtime.
        return not (src_stat.st_size == dst_stat.st_size and dst_stat.st_mtime >= src_stat.st_mtime)
    except Exception:
        return True

def copy_with_dirs(
    src: Path,
    base: Path,
    dest_root: Path,
    dest_subfolder: str,
    dry_run: bool,
    progress: Optional[Callable[[int], None]] = None,
) -> None:
    rel = src.relative_to(base)
    dest = dest_root / dest_subfolder / rel
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as source_file, dest.open("wb") as dest_file:
        while True:
            chunk = source_file.read(1024 * 1024)
            if not chunk:
                break
            dest_file.write(chunk)
            if progress:
                progress(len(chunk))
    shutil.copystat(src, dest)

# -------------------------
# Core
# -------------------------

def backup(
    sources: List[Tuple[Path, Optional[str]]],
    destination: Path,
    dry_run: bool,
    logfile: Path,
    notifier: Optional[str],
    show_progress: bool = True,
) -> None:
    start = datetime.now()
    notify("Backup", "Backup starting…", notifier)
    log_line(logfile, "Backup started")

    # Validate sources
    missing_sources = [s for (s, _) in sources if not s.exists()]
    if missing_sources:
        for s in missing_sources:
            log_line(logfile, f"Source not found: {s}")
        raise SystemExit(f"One or more sources do not exist. First missing: {missing_sources[0]}")

    if not dry_run:
        destination.mkdir(parents=True, exist_ok=True)

    # Prepare iteration
    if show_progress and sys.stderr.isatty():
        print("Scanning files...", file=sys.stderr)

    file_list: list[tuple[Path, Path, str]] = []
    copy_plan: list[tuple[Path, Path, str, int]] = []
    total_bytes = 0
    for src, explicit_name in sources:
        subfolder_name = explicit_name if explicit_name is not None else get_basename_exact(src)
        # Debug log for clarity
        log_line(logfile, f"Planning backup: {src} -> {destination / subfolder_name}")
        for f in iter_files(src):
            file_list.append((f, src, subfolder_name))
            dest_path = destination / subfolder_name / f.relative_to(src)
            if file_needs_copy(f, dest_path):
                try:
                    size = f.stat().st_size
                except Exception:
                    size = 0
                copy_plan.append((f, src, subfolder_name, size))
                total_bytes += size

    copied = 0
    progress = TextProgressBar(total_bytes, label="Copying", enabled=show_progress and not dry_run)
    try:
        for f, base, subfolder, size in copy_plan:
            copy_with_dirs(f, base, destination, subfolder, dry_run, progress.update)
            if size == 0:
                progress.render()
            copied += 1
    finally:
        progress.finish()

    end = datetime.now()
    elapsed = end - start

    if dry_run:
        notify("Backup", "Dry run complete", notifier)
        log_line(logfile, f"Dry run completed. Files evaluated: {len(file_list)}; would copy: {copied}; elapsed: {elapsed}")
        print(f"Dry run completed. Files evaluated: {len(file_list)}; would copy: {copied}; elapsed: {elapsed}")
    else:
        notify("Backup", "Backup complete", notifier)
        log_line(logfile, f"Backup completed. Files evaluated: {len(file_list)}; copied: {copied}; elapsed: {elapsed}")
        print(f"Backup completed. Files evaluated: {len(file_list)}; copied: {copied}; elapsed: {elapsed}")

# -------------------------
# CLI
# -------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Portable backup utility")
    parser.add_argument("--sources", type=str, default=os.environ.get("BACKUP_SOURCES", ""),
                        help=("Comma-separated list of sources. Each item may be "
                              "`/abs/path` or `/abs/path=Destination Subfolder Name`. "
                              "Env: BACKUP_SOURCES"))
    parser.add_argument("--dest", type=str, default=os.environ.get("BACKUP_DESTINATION", ""),
                        help="Destination directory root. Env: BACKUP_DESTINATION")
    parser.add_argument("--logfile", type=str, default=os.environ.get("BACKUP_LOGFILE", "./backup.log"),
                        help="Log file path. Env: BACKUP_LOGFILE. Default: ./backup.log")
    parser.add_argument("--notifier", type=str, default=os.environ.get("BACKUP_NOTIFIER"),
                        help="Optional path to a desktop notification binary (e.g., terminal-notifier). Env: BACKUP_NOTIFIER")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without copying")
    parser.add_argument("--no-progress", action="store_true", help="Disable the text progress bar")

    args = parser.parse_args()

    if not args.sources:
        raise SystemExit("No sources provided. Use --sources or BACKUP_SOURCES env.")
    if not args.dest:
        raise SystemExit("No destination provided. Use --dest or BACKUP_DESTINATION env.")

    sources = parse_sources_with_mapping(args.sources)
    destination = Path(args.dest).expanduser().resolve()
    logfile = Path(args.logfile).expanduser().resolve()

    try:
        backup(sources, destination, args.dry_run, logfile, args.notifier, not args.no_progress)
    except KeyboardInterrupt:
        log_line(Path(args.logfile), "Backup interrupted by user")
        notify("Backup", "Backup interrupted", args.notifier)
        print("\nBackup interrupted by user.")
        raise SystemExit(130)

if __name__ == "__main__":
    main()
