#!/usr/bin/env python3
"""
read_e01.py — Browse and extract files from E01 forensic images.

Requires (preferred):
  pip install pyewf pytsk3

Or install system packages (Debian/Ubuntu):
  sudo apt-get install python3-libewf python3-tsk ewf-tools

If pyewf/pytsk3 are not available the 'info' subcommand falls back to the
bundled ewfinfo executable (ewf/ewfinfo.exe on Windows, ewfinfo on Linux).

Subcommands:
  info     <image.E01> [...]   — Show EWF metadata / case information
  ls       <image.E01> [path]  — List directory contents inside the image
  tree     <image.E01> [path]  — Recursive directory listing
  cat      <image.E01> <path>  — Print file contents to stdout
  extract  <image.E01> <path> <dest_dir>
                               — Extract a file or directory to dest_dir

Examples:
  python read_e01.py info disk.E01
  python read_e01.py ls  disk.E01 /
  python read_e01.py ls  disk.E01 /Windows/System32
  python read_e01.py tree disk.E01 /Users
  python read_e01.py cat  disk.E01 /Windows/System32/drivers/etc/hosts
  python read_e01.py extract disk.E01 /Documents C:\\output
"""

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EWF_DIR = os.path.join(SCRIPT_DIR, "ewf")

# ---------------------------------------------------------------------------
# Optional heavy imports
# ---------------------------------------------------------------------------
try:
    import pyewf  # type: ignore
    import pytsk3  # type: ignore
    _HAS_PYEWF = True
except ImportError:
    _HAS_PYEWF = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ewfinfo_fallback(images: list[str]) -> int:
    """Run the bundled ewfinfo executable as a fallback for the info command."""
    exe = os.path.join(EWF_DIR, "ewfinfo.exe")
    if not os.path.isfile(exe):
        exe = "ewfinfo"  # hope it is on PATH
    try:
        result = subprocess.run([exe] + images)
        return result.returncode
    except FileNotFoundError:
        print(
            "[read_e01] ERROR: ewfinfo not found.\n"
            "Install ewf-tools or place ewfinfo.exe in the ewf/ directory.",
            file=sys.stderr,
        )
        return 1


class _EWFImgInfo(pytsk3.Img_Info):  # type: ignore
    """Bridge between pyewf and pytsk3."""

    def __init__(self, handle):
        self._handle = handle
        super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

    def close(self):
        self._handle.close()

    def read(self, offset, length):
        self._handle.seek(offset)
        return self._handle.read(length)

    def get_size(self):
        return self._handle.get_media_size()


def _open_image(images: list[str]):
    """Open a pyewf handle and return an _EWFImgInfo and a pytsk3.FS_Info."""
    handle = pyewf.handle()
    handle.open(images)
    img = _EWFImgInfo(handle)
    # Try to detect offset automatically; fall back to 0.
    try:
        vol = pytsk3.Volume_Info(img)
        for part in vol:
            if part.flags == pytsk3.TSK_VS_PART_FLAG_ALLOC:
                offset = part.start * 512
                break
        else:
            offset = 0
    except Exception:
        offset = 0
    fs = pytsk3.FS_Info(img, offset=offset)
    return img, fs


def _norm(path: str) -> str:
    """Normalise a path for pytsk3 (always use forward slashes, no trailing /)."""
    p = path.replace("\\", "/")
    if p != "/" and p.endswith("/"):
        p = p.rstrip("/")
    return p or "/"


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------

def cmd_info(images: list[str]) -> int:
    if not _HAS_PYEWF:
        return _ewfinfo_fallback(images)
    try:
        handle = pyewf.handle()
        handle.open(images)
        headers = handle.get_header_values()
        hash_values = handle.get_hash_values()
        media_size = handle.get_media_size()
        handle.close()
    except Exception as exc:
        print(f"[read_e01] ERROR opening image: {exc}", file=sys.stderr)
        return 1

    print("=== EWF Image Information ===")
    print(f"Media size : {media_size:,} bytes ({media_size / (1024**3):.2f} GiB)")
    if headers:
        print("\n--- Header values ---")
        for k, v in headers.items():
            print(f"  {k}: {v}")
    if hash_values:
        print("\n--- Hash values ---")
        for k, v in hash_values.items():
            print(f"  {k}: {v}")
    return 0


def cmd_ls(images: list[str], path: str = "/") -> int:
    if not _HAS_PYEWF:
        print("[read_e01] ERROR: pyewf/pytsk3 required for ls.", file=sys.stderr)
        return 1
    try:
        img, fs = _open_image(images)
    except Exception as exc:
        print(f"[read_e01] ERROR: {exc}", file=sys.stderr)
        return 1

    path = _norm(path)
    try:
        directory = fs.open_dir(path=path)
    except Exception as exc:
        print(f"[read_e01] ERROR opening directory '{path}': {exc}", file=sys.stderr)
        return 1

    for entry in directory:
        name = entry.info.name.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name in (".", ".."):
            continue
        meta = entry.info.meta
        if meta is None:
            kind = "?"
        elif meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            kind = "d"
        else:
            kind = "-"
        size = meta.size if meta else 0
        print(f"{kind}  {size:>12,}  {name}")
    img.close()
    return 0


def _tree_recursive(directory, fs, prefix: str = "") -> None:
    for entry in directory:
        name = entry.info.name.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name in (".", ".."):
            continue
        meta = entry.info.meta
        is_dir = meta is not None and meta.type == pytsk3.TSK_FS_META_TYPE_DIR
        print(f"{prefix}{name}{'/' if is_dir else ''}")
        if is_dir and meta.flags & pytsk3.TSK_FS_META_FLAG_ALLOC:
            try:
                sub_path = entry.info.name.name
                if isinstance(sub_path, bytes):
                    sub_path = sub_path.decode("utf-8", errors="replace")
                sub_dir = fs.open_dir(inode=meta.addr)
                _tree_recursive(sub_dir, fs, prefix + "  ")
            except Exception:
                pass


def cmd_tree(images: list[str], path: str = "/") -> int:
    if not _HAS_PYEWF:
        print("[read_e01] ERROR: pyewf/pytsk3 required for tree.", file=sys.stderr)
        return 1
    try:
        img, fs = _open_image(images)
    except Exception as exc:
        print(f"[read_e01] ERROR: {exc}", file=sys.stderr)
        return 1

    path = _norm(path)
    try:
        directory = fs.open_dir(path=path)
    except Exception as exc:
        print(f"[read_e01] ERROR opening directory '{path}': {exc}", file=sys.stderr)
        return 1

    print(path)
    _tree_recursive(directory, fs)
    img.close()
    return 0


def cmd_cat(images: list[str], path: str) -> int:
    if not _HAS_PYEWF:
        print("[read_e01] ERROR: pyewf/pytsk3 required for cat.", file=sys.stderr)
        return 1
    try:
        img, fs = _open_image(images)
    except Exception as exc:
        print(f"[read_e01] ERROR: {exc}", file=sys.stderr)
        return 1

    path = _norm(path)
    try:
        f = fs.open(path)
    except Exception as exc:
        print(f"[read_e01] ERROR opening '{path}': {exc}", file=sys.stderr)
        return 1

    size = f.info.meta.size
    offset = 0
    chunk = 1024 * 1024
    out = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout
    while offset < size:
        to_read = min(chunk, size - offset)
        data = f.read_random(offset, to_read)
        out.write(data)
        offset += to_read
    img.close()
    return 0


def _extract_file(f, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    size = f.info.meta.size
    offset = 0
    chunk = 1024 * 1024
    with open(dest_path, "wb") as out:
        while offset < size:
            to_read = min(chunk, size - offset)
            data = f.read_random(offset, to_read)
            out.write(data)
            offset += to_read


def _extract_dir(directory, fs, dest_base: str) -> None:
    os.makedirs(dest_base, exist_ok=True)
    for entry in directory:
        name = entry.info.name.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name in (".", ".."):
            continue
        meta = entry.info.meta
        dest = os.path.join(dest_base, name)
        if meta is not None and meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            try:
                sub_dir = fs.open_dir(inode=meta.addr)
                _extract_dir(sub_dir, fs, dest)
            except Exception:
                pass
        else:
            try:
                f = fs.open(inode=meta.addr)
                _extract_file(f, dest)
                print(f"  extracted: {dest}")
            except Exception:
                pass


def cmd_extract(images: list[str], src_path: str, dest_dir: str) -> int:
    if not _HAS_PYEWF:
        print("[read_e01] ERROR: pyewf/pytsk3 required for extract.", file=sys.stderr)
        return 1
    try:
        img, fs = _open_image(images)
    except Exception as exc:
        print(f"[read_e01] ERROR: {exc}", file=sys.stderr)
        return 1

    src_path = _norm(src_path)
    os.makedirs(dest_dir, exist_ok=True)

    # Try directory first
    try:
        directory = fs.open_dir(path=src_path)
        basename = os.path.basename(src_path.rstrip("/")) or "root"
        _extract_dir(directory, fs, os.path.join(dest_dir, basename))
        img.close()
        return 0
    except Exception:
        pass

    # Try file
    try:
        f = fs.open(src_path)
        basename = os.path.basename(src_path)
        dest_path = os.path.join(dest_dir, basename)
        _extract_file(f, dest_path)
        print(f"  extracted: {dest_path}")
        img.close()
        return 0
    except Exception as exc:
        print(f"[read_e01] ERROR extracting '{src_path}': {exc}", file=sys.stderr)
        img.close()
        return 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Browse and extract files from E01 forensic images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # info
    p_info = sub.add_parser("info", help="Show EWF metadata")
    p_info.add_argument("images", nargs="+", metavar="image.E01")

    # ls
    p_ls = sub.add_parser("ls", help="List directory contents")
    p_ls.add_argument("images", nargs="+", metavar="image.E01")
    p_ls.add_argument("--path", default="/", help="Directory path inside image (default: /)")

    # tree
    p_tree = sub.add_parser("tree", help="Recursive directory listing")
    p_tree.add_argument("images", nargs="+", metavar="image.E01")
    p_tree.add_argument("--path", default="/", help="Starting path (default: /)")

    # cat
    p_cat = sub.add_parser("cat", help="Print file contents to stdout")
    p_cat.add_argument("images", nargs="+", metavar="image.E01")
    p_cat.add_argument("--path", required=True, help="Path to the file inside the image")

    # extract
    p_ext = sub.add_parser("extract", help="Extract file or directory")
    p_ext.add_argument("images", nargs="+", metavar="image.E01")
    p_ext.add_argument("--path", required=True, help="Source path inside the image")
    p_ext.add_argument("--dest", required=True, help="Destination directory on the host")

    args = parser.parse_args()

    dispatch = {
        "info":    lambda: cmd_info(args.images),
        "ls":      lambda: cmd_ls(args.images, args.path),
        "tree":    lambda: cmd_tree(args.images, args.path),
        "cat":     lambda: cmd_cat(args.images, args.path),
        "extract": lambda: cmd_extract(args.images, args.path, args.dest),
    }
    sys.exit(dispatch[args.subcommand]())


if __name__ == "__main__":
    main()
