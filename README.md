# EWF — Expert Witness Format (E01) Tools

This repository provides Python CLI scripts for creating, managing, and reading
**E01 forensic disk images** using the bundled EWF executables.

---

## Repository structure

```
ewf/              Bundled EWF executables (ewfinfo.exe, ewfacquire.exe, …)
ewf_tools.py      CLI wrapper for all bundled EWF tools
read_e01.py       Tool for browsing / extracting content from E01 images
commands          Quick-reference command examples
```

---

## ewf_tools.py

A Python wrapper around the bundled EWF tools.  On **Windows** the bundled
`.exe` files are used directly.  On **Linux/macOS** install either Wine (to run
the bundled executables) or the native `ewf-tools` package:

```bash
sudo apt-get install ewf-tools     # Ubuntu / Debian
```

### Subcommands

| Subcommand       | Underlying tool        | Description                                         |
|------------------|------------------------|-----------------------------------------------------|
| `info`           | ewfinfo                | Display metadata about an E01 image                 |
| `acquire`        | ewfacquire             | Create an E01 image from a raw disk / image file    |
| `acquire-stream` | ewfacquirestream       | Create an E01 image by reading from stdin or a file |
| `export`         | ewfexport              | Export an E01 image to another format               |
| `verify`         | ewfverify              | Verify the integrity of an E01 image                |
| `recover`        | ewfrecover             | Recover a damaged E01 image                         |
| `mount`          | ewfmount               | Mount an E01 image at a directory                   |
| `debug`          | ewfdebug               | Display internal debug information                  |

### Usage examples

```bash
# Show metadata
python ewf_tools.py info image.E01

# Create an E01 image from a raw .001 file (5 GB max segment size)
python ewf_tools.py acquire -f ewf -S 5000000000 -t /output/image source.001

# Create an E01 image from stdin
dd if=/dev/sdb | python ewf_tools.py acquire-stream -t /output/image

# Create an E01 image from a file (redirected as stdin)
python ewf_tools.py acquire-stream --input source.raw -t /output/image

# Export E01 segments to a raw image
python ewf_tools.py export -t /output/raw image.E01 image.E02 image.E03

# Verify image integrity
python ewf_tools.py verify image.E01

# Mount the image (Linux with ewfmount)
mkdir /mnt/ewf
python ewf_tools.py mount image.E01 /mnt/ewf

# Display debug info
python ewf_tools.py debug image.E01
```

---

## read_e01.py

A Python tool for **browsing and extracting** the filesystem contained in an
E01 image.  Requires `pyewf` and `pytsk3`:

```bash
sudo apt-get install python3-libewf python3-tsk ewf-tools
```

The `info` subcommand falls back to the bundled `ewfinfo.exe` (or the system
`ewfinfo`) when `pyewf` is not installed.

### Subcommands

| Subcommand | Description                                          |
|------------|------------------------------------------------------|
| `info`     | Print E01 metadata (case info, hash values, size)    |
| `ls`       | List files/directories at a given path               |
| `tree`     | Recursively list all files/directories               |
| `cat`      | Print raw content of a file inside the image         |
| `extract`  | Extract a file or directory to a local path          |

### Usage examples

```bash
# Show image metadata
python read_e01.py info image.E01

# List root directory
python read_e01.py ls image.E01 /

# List a subdirectory
python read_e01.py ls image.E01 /Windows/System32

# Full recursive directory tree
python read_e01.py tree image.E01

# Print a text file to stdout
python read_e01.py cat image.E01 /Windows/System32/drivers/etc/hosts

# Extract a single file
python read_e01.py extract image.E01 /Windows/System32/drivers/etc/hosts ./hosts

# Extract an entire directory
python read_e01.py extract image.E01 /Windows/System32 ./System32_dump
```

---

## Requirements

| Tool / library   | Purpose                                   | Install                                    |
|------------------|-------------------------------------------|--------------------------------------------|
| Python 3.10+     | Running the scripts                       | https://python.org                         |
| pyewf            | Open E01 images from Python               | `sudo apt-get install python3-libewf`      |
| pytsk3           | Filesystem access (ls / tree / cat / extract) | `sudo apt-get install python3-tsk`     |
| ewf-tools        | Native Linux EWF tools (ewfinfo, etc.)    | `sudo apt-get install ewf-tools`           |
| Wine *(Windows exe fallback)* | Run bundled `.exe` on Linux  | `sudo apt-get install wine`                |
