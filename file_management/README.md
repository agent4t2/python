# USB Backup Utility

`usb-backup.py` is a small, portable Python backup script for copying one or more source folders to a destination folder, such as a mounted USB drive or external disk.

The script keeps each source in its own destination subfolder, skips files that are already up to date, writes a timestamped log, and displays a built-in text progress bar while files are copied.

## Features

- Back up one or more source directories.
- Preserve each source directory under its own destination subfolder.
- Optionally rename the destination subfolder for each source.
- Skip files that already exist at the destination when size matches and the destination file is newer or the same age.
- Ignore hidden files and hidden directories.
- Preserve copied file metadata using Python's file stat copying.
- Show byte-level terminal progress during copying.
- Support dry-run mode.
- Write timestamped log messages.
- Optionally call a desktop notification command.

## Requirements

- Python 3.9 or newer is recommended.
- No third-party Python packages are required.

The script uses only the Python standard library.

## Quick Start

Run the script with at least one source folder and one destination folder:

```bash
python3 usb-backup.py \
  --sources "/Users/example/Documents" \
  --dest "/Volumes/MyUSB/Backups"
```

This creates a backup like:

```text
/Volumes/MyUSB/Backups/Documents/
```

## Multiple Sources

Separate sources with commas:

```bash
python3 usb-backup.py \
  --sources "/Users/example/Documents,/Users/example/Pictures" \
  --dest "/Volumes/MyUSB/Backups"
```

The destination will contain one subfolder for each source:

```text
/Volumes/MyUSB/Backups/Documents/
/Volumes/MyUSB/Backups/Pictures/
```

## Custom Destination Subfolder Names

Use `source=Subfolder Name` to choose the destination subfolder name:

```bash
python3 usb-backup.py \
  --sources "/Users/example/Documents=Work Docs,/Users/example/Pictures=Photo Archive" \
  --dest "/Volumes/MyUSB/Backups"
```

The destination will look like:

```text
/Volumes/MyUSB/Backups/Work Docs/
/Volumes/MyUSB/Backups/Photo Archive/
```

## Environment Variables

Instead of passing every option on the command line, you can use environment variables:

```bash
export BACKUP_SOURCES="/Users/example/Documents,/Users/example/Pictures"
export BACKUP_DESTINATION="/Volumes/MyUSB/Backups"
export BACKUP_LOGFILE="/Users/example/backup.log"

python3 usb-backup.py
```

## Command-Line Options

| Option | Environment variable | Description |
| --- | --- | --- |
| `--sources` | `BACKUP_SOURCES` | Comma-separated source folders. Each source can optionally use `source=Destination Name`. |
| `--dest` | `BACKUP_DESTINATION` | Destination root folder where backup subfolders will be created. |
| `--logfile` | `BACKUP_LOGFILE` | Path to the log file. Defaults to `./backup.log`. |
| `--notifier` | `BACKUP_NOTIFIER` | Optional path to a notification command, such as `terminal-notifier`. |
| `--dry-run` | None | Simulate the backup without copying files. |
| `--no-progress` | None | Disable the terminal progress bar. Useful for scheduled or non-interactive runs. |

## How It Works

1. The script reads sources and destination from command-line options or environment variables.
2. It verifies that all source paths exist.
3. It scans each source directory recursively.
4. Hidden files and directories are skipped.
5. Each source is mapped into a destination subfolder.
6. The script builds a copy plan containing only files that need to be copied.
7. Files are copied in chunks so the progress bar can update during large file copies.
8. File metadata is copied after each file is written.
9. A summary is printed and written to the log file.

## Progress Bar

During an interactive terminal run, the script displays a byte-based progress bar:

```text
Scanning files...
Copying: [####################################] 100.00% 8.0 KB / 8.0 KB
```

The progress bar is based on the total size of files that actually need to be copied. Files that are already up to date are excluded from the progress total.

To disable progress output:

```bash
python3 usb-backup.py \
  --sources "/Users/example/Documents" \
  --dest "/Volumes/MyUSB/Backups" \
  --no-progress
```

## Dry Run

Use `--dry-run` to see what the script would evaluate and copy without writing files:

```bash
python3 usb-backup.py \
  --sources "/Users/example/Documents" \
  --dest "/Volumes/MyUSB/Backups" \
  --dry-run
```

## Logging

By default, the script writes to `./backup.log` in the current working directory.

To choose a log file:

```bash
python3 usb-backup.py \
  --sources "/Users/example/Documents" \
  --dest "/Volumes/MyUSB/Backups" \
  --logfile "/Users/example/usb-backup.log"
```

Log entries include timestamps and backup summary details.

## Notifications

The script can optionally call an external notification command. For example, on macOS you can use a tool such as `terminal-notifier`:

```bash
python3 usb-backup.py \
  --sources "/Users/example/Documents" \
  --dest "/Volumes/MyUSB/Backups" \
  --notifier "/usr/local/bin/terminal-notifier"
```

The notification command is optional. If no notifier is provided, the backup still runs normally.

## Backup Behavior Notes

- Existing destination files are skipped when they have the same size as the source and their modification time is newer than or equal to the source.
- If a destination file is missing, older, or a different size, it is copied.
- Hidden files and folders are skipped when any path component starts with `.`.
- The script does not delete destination files that no longer exist in the source.
- The script is intended for directory backups. Source paths should be folders.

## Example

```bash
python3 usb-backup.py \
  --sources "/Users/username/Documents=Documents Backup,/Users/username/Pictures=Pictures Backup" \
  --dest "/Volumes/USBDrive/Backups" \
  --logfile "/Users/username/usb-backup.log"
```

This copies changed files into:

```text
/Volumes/USBDrive/Backups/Documents Backup/
/Volumes/USBDrive/Backups/Pictures Backup/
```
