#!/usr/bin/env python3
"""
read_e01.py - Browse and extract content from E01 (Expert Witness Format) images.

This tool uses pyewf and pytsk3 as the primary backend for full filesystem
access.  When pyewf/pytsk3 are not installed, the 'info' subcommand falls back
to the bundled ewfinfo executable (or the system ewfinfo on PATH).

Install dependencies (Linux):
    sudo apt-get install python3-libewf python3-tsk ewf-tools

Subcommands:
  info      Print E01 metadata (case info, hash values, media size, etc.)
  ls        List files/directories at a given path inside the image
  tree      Recursively list all files/directories inside the image
  cat       Print the raw content of a file inside the image to stdout
  extract   Extract a file or directory from the image to a local path

Examples:
  python read_e01.py info image.E01
  python read_e01.py ls image.E01 /
  python read_e01.py ls image.E01 /Windows/System32
  python read_e01.py tree image.E01
  python read_e01.py cat image.E01 /Windows/System32/drivers/etc/hosts
  python read_e01.py extract image.E01 /Windows/System32/drivers/etc/hosts ./hosts
  python read_e01.py extract image.E01 /Windows/System32 ./System32_dump
"""

import argparse
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EWF_DIR = os.path.join(SCRIPT_DIR, "ewf")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_ewfinfo() -> str | None:
    """Return path to ewfinfo: check bundled .exe first, then system PATH."""
    bundled = os.path.join(EWF_DIR, "ewfinfo.exe")
    if os.path.isfile(bundled):
        return bundled
    return shutil.which("ewfinfo")


def _check_dependencies():
    """Import pyewf and pytsk3, raising ImportError with helpful message if absent."""
    try:
        import pyewf  # noqa: F401
        import pytsk3  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            f"Required library not found: {exc}\n"
            "Install with:  sudo apt-get install python3-libewf python3-tsk\n"
            "On Windows:    pip install pyewf pytsk3"
        ) from exc


# ---------------------------------------------------------------------------
# pyewf / pytsk3 backend
# ---------------------------------------------------------------------------

class EWFImgInfo:
    """pytsk3 Img_Info adapter that reads from an open pyewf handle."""

    def __init__(self, ewf_handle):
        import pytsk3
        self._ewf_handle = ewf_handle
        self._img_info = pytsk3.Img_Info.__new__(pytsk3.Img_Info)

    # pytsk3 calls these methods via its C extension
    def read(self, offset: int, length: int) -> bytes:
        self._ewf_handle.seek(offset)
        return self._ewf_handle.read(length)

    def get_size(self) -> int:
        return self._ewf_handle.get_media_size()


def _open_filesystem(image_path: str):
    """Open an E01 image and return (ewf_handle, fs_info) using pyewf + pytsk3."""
    import pyewf
    import pytsk3

    filenames = pyewf.glob(image_path)
    ewf_handle = pyewf.handle()
    ewf_handle.open(filenames)

    img = EWFImgInfo(ewf_handle)
    # Attempt to find a partition table; fall back to treating the whole image
    # as a single filesystem volume.
    try:
        volume = pytsk3.Volume_Info(img)
        for part in volume:
            if part.flags == pytsk3.TSK_VS_PART_FLAG_ALLOC:
                offset = part.start * 512
                try:
                    fs = pytsk3.FS_Info(img, offset=offset)
                    return ewf_handle, fs
                except OSError:
                    continue
    except OSError:
        pass

    # No recognised partition table — treat the image as a raw filesystem
    fs = pytsk3.FS_Info(img)
    return ewf_handle, fs


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def cmd_info(args: argparse.Namespace) -> None:
    """Display E01 metadata."""
    # Try pyewf first for rich metadata
    try:
        _check_dependencies()
        import pyewf

        filenames = pyewf.glob(args.image)
        handle = pyewf.handle()
        handle.open(filenames)

        print(f"Image file   : {args.image}")
        print(f"Media size   : {handle.get_media_size()} bytes")

        # Print header values if available
        try:
            headers = handle.get_header_values()
            if headers:
                print("\nHeader values:")
                for key, value in headers.items():
                    print(f"  {key}: {value}")
        except Exception:
            pass

        # Print hash values if available
        try:
            hashes = handle.get_hash_values()
            if hashes:
                print("\nHash values:")
                for key, value in hashes.items():
                    print(f"  {key}: {value}")
        except Exception:
            pass

        handle.close()
        return

    except ImportError:
        pass

    # Fallback: use bundled/system ewfinfo
    ewfinfo = find_ewfinfo()
    if not ewfinfo:
        print(
            "Error: 'ewfinfo' not found and pyewf is not installed.\n"
            "Install pyewf:   sudo apt-get install python3-libewf\n"
            "or ewf-tools:    sudo apt-get install ewf-tools",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        result = subprocess.run([ewfinfo, args.image], check=False)
        sys.exit(result.returncode)
    except (FileNotFoundError, PermissionError, OSError):
        print(
            f"Error: cannot execute '{ewfinfo}'.\n"
            "On Linux, install Wine to run the bundled .exe, "
            "or install 'ewf-tools' for native Linux binaries.",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_ls(args: argparse.Namespace) -> None:
    """List directory contents inside an E01 image."""
    try:
        _check_dependencies()
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ewf_handle, fs = _open_filesystem(args.image)
    try:
        path = args.path or "/"
        directory = fs.open_dir(path=path)
        for entry in directory:
            name = entry.info.name.name
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            if name in (".", ".."):
                continue
            meta = entry.info.meta
            if meta:
                size = meta.size
                ftype = "d" if meta.type == 2 else "-"  # TSK_FS_META_TYPE_DIR == 2
                print(f"{ftype}  {size:>12}  {name}")
            else:
                print(f"?  {'':>12}  {name}")
    finally:
        ewf_handle.close()


def _tree_dir(fs, path: str, prefix: str = "") -> None:
    """Recursively print directory tree."""
    import pytsk3

    try:
        directory = fs.open_dir(path=path)
    except OSError as exc:
        print(f"{prefix}[error reading directory: {exc}]")
        return

    entries = []
    for entry in directory:
        name = entry.info.name.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name in (".", ".."):
            continue
        entries.append((name, entry.info.meta))

    for i, (name, meta) in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        print(f"{prefix}{connector}{name}")
        if meta and meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            extension = "    " if i == len(entries) - 1 else "│   "
            child_path = (path.rstrip("/") + "/" + name)
            _tree_dir(fs, child_path, prefix + extension)


def cmd_tree(args: argparse.Namespace) -> None:
    """Recursively list all files inside an E01 image."""
    try:
        _check_dependencies()
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ewf_handle, fs = _open_filesystem(args.image)
    try:
        print(args.image)
        _tree_dir(fs, "/")
    finally:
        ewf_handle.close()


def cmd_cat(args: argparse.Namespace) -> None:
    """Print the content of a file inside an E01 image to stdout."""
    try:
        _check_dependencies()
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ewf_handle, fs = _open_filesystem(args.image)
    try:
        f = fs.open(args.path)
        size = f.info.meta.size
        offset = 0
        chunk = 1024 * 1024  # 1 MB chunks
        buf = sys.stdout.buffer
        while offset < size:
            to_read = min(chunk, size - offset)
            data = f.read_random(offset, to_read)
            if not data:
                break
            buf.write(data)
            offset += len(data)
    finally:
        ewf_handle.close()


def _extract_entry(fs, img_path: str, local_path: str) -> None:
    """Extract a single file or directory from the image to a local path."""
    import pytsk3

    entry = fs.open(img_path)
    meta = entry.info.meta

    if meta and meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
        os.makedirs(local_path, exist_ok=True)
        directory = fs.open_dir(path=img_path)
        for child in directory:
            name = child.info.name.name
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="replace")
            if name in (".", ".."):
                continue
            child_img = img_path.rstrip("/") + "/" + name
            child_local = os.path.join(local_path, name)
            try:
                _extract_entry(fs, child_img, child_local)
            except OSError as exc:
                print(f"Warning: skipping '{child_img}': {exc}", file=sys.stderr)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        size = meta.size if meta else 0
        offset = 0
        chunk = 1024 * 1024
        with open(local_path, "wb") as fh:
            while offset < size:
                to_read = min(chunk, size - offset)
                data = entry.read_random(offset, to_read)
                if not data:
                    break
                fh.write(data)
                offset += len(data)


def cmd_extract(args: argparse.Namespace) -> None:
    """Extract a file or directory from an E01 image to a local path."""
    try:
        _check_dependencies()
    except ImportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ewf_handle, fs = _open_filesystem(args.image)
    try:
        _extract_entry(fs, args.path, args.dest)
        print(f"Extracted '{args.path}' -> '{args.dest}'")
    finally:
        ewf_handle.close()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="read_e01.py",
        description=(
            "Browse and extract content from E01 (Expert Witness Format) images.\n"
            "Requires pyewf + pytsk3 for filesystem access (ls, tree, cat, extract).\n"
            "The 'info' subcommand falls back to the bundled ewfinfo when pyewf is absent."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- info ----------------------------------------------------------------
    p_info = subparsers.add_parser(
        "info", help="Print E01 metadata (case info, hash values, media size)"
    )
    p_info.add_argument("image", metavar="IMAGE", help="Path to the first E01 segment")
    p_info.set_defaults(func=cmd_info)

    # -- ls ------------------------------------------------------------------
    p_ls = subparsers.add_parser(
        "ls", help="List files/directories at a path inside the image"
    )
    p_ls.add_argument("image", metavar="IMAGE", help="Path to the first E01 segment")
    p_ls.add_argument(
        "path", metavar="PATH", nargs="?", default="/",
        help="Path inside the image (default: /)",
    )
    p_ls.set_defaults(func=cmd_ls)

    # -- tree ----------------------------------------------------------------
    p_tree = subparsers.add_parser(
        "tree", help="Recursively list all files/directories inside the image"
    )
    p_tree.add_argument("image", metavar="IMAGE", help="Path to the first E01 segment")
    p_tree.set_defaults(func=cmd_tree)

    # -- cat -----------------------------------------------------------------
    p_cat = subparsers.add_parser(
        "cat", help="Print the raw content of a file inside the image to stdout"
    )
    p_cat.add_argument("image", metavar="IMAGE", help="Path to the first E01 segment")
    p_cat.add_argument("path", metavar="PATH", help="Path of the file inside the image")
    p_cat.set_defaults(func=cmd_cat)

    # -- extract -------------------------------------------------------------
    p_ext = subparsers.add_parser(
        "extract", help="Extract a file or directory from the image to a local path"
    )
    p_ext.add_argument("image", metavar="IMAGE", help="Path to the first E01 segment")
    p_ext.add_argument("path", metavar="PATH", help="Path of the file/dir inside the image")
    p_ext.add_argument(
        "dest", metavar="DEST", help="Local destination path"
    )
    p_ext.set_defaults(func=cmd_extract)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
