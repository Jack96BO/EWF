#!/usr/bin/env python3
"""
read_e01.py - Browse and extract files from E01/EWF forensic images.

Supports two backends, selected automatically:
  1. pyewf + pytsk3  (preferred) - full filesystem-aware access.
  2. ewfexport fallback           - exports a sector range to a temporary raw
     image and uses the 'file' command for basic type detection when
     pyewf/pytsk3 are not installed.

Installation of the preferred backend (Linux):
    sudo apt-get install libewf-dev libtsk-dev python3-dev
    pip install pyewf pytsk3

On Windows the bundled ewf/ewfexport.exe is used for the fallback backend.

Usage:
    python read_e01.py info   <image.E01> [<image.E02> ...]
    python read_e01.py ls     <image.E01> [path]
    python read_e01.py tree   <image.E01> [path] [--max-depth N]
    python read_e01.py cat    <image.E01> <internal_path>
    python read_e01.py extract <image.E01> <internal_path> [--output OUTPUT]
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_EWF_DIR = os.path.join(_SCRIPT_DIR, "ewf")


def _have_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


_HAVE_PYEWF = _have_module("pyewf")
_HAVE_PYTSK3 = _have_module("pytsk3")
_NATIVE_BACKEND = _HAVE_PYEWF and _HAVE_PYTSK3


def _resolve_tool(name: str) -> str | None:
    """Return the path to an ewf tool, or None if not found."""
    native = shutil.which(name)
    if native:
        return native
    exe_name = name + ".exe"
    bundled = os.path.join(_EWF_DIR, exe_name)
    if os.path.isfile(bundled):
        return bundled
    return None


# ---------------------------------------------------------------------------
# Native backend helpers (pyewf + pytsk3)
# ---------------------------------------------------------------------------


def _open_ewf(images: list):
    """Open an EWF image using pyewf and return a pyewf.handle."""
    import pyewf  # noqa: F401 - already checked above

    filenames = pyewf.glob(images[0])
    handle = pyewf.handle()
    handle.open(filenames)
    return handle


def _open_img_info(images: list):
    """Return a pytsk3.Img_Info backed by pyewf."""
    import pyewf
    import pytsk3

    class EWFImgInfo(pytsk3.Img_Info):
        def __init__(self, ewf_handle):
            self._ewf_handle = ewf_handle
            super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

        def close(self):
            self._ewf_handle.close()

        def read(self, offset, length):
            self._ewf_handle.seek(offset)
            return self._ewf_handle.read(length)

        def get_size(self):
            return self._ewf_handle.get_media_size()

    handle = _open_ewf(images)
    return EWFImgInfo(handle)


def _open_fs(images: list, partition_offset: int = 0):
    """Open the filesystem inside an EWF image using pytsk3."""
    import pytsk3

    img_info = _open_img_info(images)
    try:
        fs_info = pytsk3.FS_Info(img_info, offset=partition_offset)
        return img_info, fs_info
    except Exception:
        # Try to detect partition table and use first partition
        try:
            volume = pytsk3.Volume_Info(img_info)
            for part in volume:
                if part.addr > 1 and part.len > 2048:
                    offset = part.start * 512
                    try:
                        fs_info = pytsk3.FS_Info(img_info, offset=offset)
                        return img_info, fs_info
                    except Exception:
                        continue
        except Exception:
            pass
        raise


def _walk_dir(fs_info, path: str, max_depth: int, current_depth: int = 0):
    """Recursively yield (depth, is_dir, full_path) tuples."""
    import pytsk3

    try:
        directory = fs_info.open_dir(path=path)
    except Exception:
        return
    for entry in directory:
        name = entry.info.name.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name in (".", ".."):
            continue
        full_path = path.rstrip("/") + "/" + name
        is_dir = entry.info.meta is not None and entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR
        yield current_depth, is_dir, full_path
        if is_dir and (max_depth < 0 or current_depth < max_depth - 1):
            yield from _walk_dir(fs_info, full_path, max_depth, current_depth + 1)


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_info(args: argparse.Namespace) -> int:
    """Display metadata and case information stored in an E01 image."""
    if _HAVE_PYEWF:
        import pyewf

        filenames = pyewf.glob(args.image[0])
        handle = pyewf.handle()
        handle.open(filenames)

        print("=== E01 Image Information ===")
        print(f"Filename(s)   : {', '.join(filenames)}")
        print(f"Media size    : {handle.get_media_size():,} bytes "
              f"({handle.get_media_size() / (1024**3):.2f} GiB)")
        print(f"Chunk count   : {handle.get_number_of_chunks():,}")
        print(f"Sectors/chunk : {handle.get_sectors_per_chunk():,}")
        print(f"Bytes/sector  : {handle.get_bytes_per_sector():,}")

        print("\n=== Header Values ===")
        for i in range(handle.get_number_of_header_values()):
            try:
                identifier = handle.get_header_value_identifier(i)
                value = handle.get_header_value(identifier)
                print(f"  {identifier:<20}: {value}")
            except Exception:
                pass

        print("\n=== Hash Values ===")
        for i in range(handle.get_number_of_hash_values()):
            try:
                identifier = handle.get_hash_value_identifier(i)
                value = handle.get_hash_value(identifier)
                print(f"  {identifier:<20}: {value}")
            except Exception:
                pass

        handle.close()
        return 0

    # Fallback: use ewfinfo
    tool = _resolve_tool("ewfinfo")
    if tool is None:
        print(
            "[ERROR] Neither pyewf nor ewfinfo is available. "
            "Install pyewf or ewf-tools.",
            file=sys.stderr,
        )
        return 1
    result = subprocess.run([tool] + args.image)
    return result.returncode


def cmd_ls(args: argparse.Namespace) -> int:
    """List files and directories at a path inside an E01 image."""
    if not _NATIVE_BACKEND:
        print(
            "[ERROR] 'ls' requires pyewf and pytsk3.\n"
            "Install them with: pip install pyewf pytsk3\n"
            "(you may also need: sudo apt-get install libewf-dev libtsk-dev)",
            file=sys.stderr,
        )
        return 1

    import pytsk3

    path = args.path or "/"
    try:
        img_info, fs_info = _open_fs(args.image)
    except Exception as exc:
        print(f"[ERROR] Could not open filesystem: {exc}", file=sys.stderr)
        return 1

    try:
        directory = fs_info.open_dir(path=path)
    except Exception as exc:
        print(f"[ERROR] Could not open path '{path}': {exc}", file=sys.stderr)
        img_info.close()
        return 1

    print(f"Contents of {path}:")
    print(f"{'Type':<6}  {'Size':>12}  {'Name'}")
    print("-" * 40)
    for entry in directory:
        name = entry.info.name.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name in (".", ".."):
            continue
        is_dir = (
            entry.info.meta is not None
            and entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR
        )
        size = entry.info.meta.size if entry.info.meta else 0
        type_str = "DIR" if is_dir else "FILE"
        print(f"{type_str:<6}  {size:>12,}  {name}")

    img_info.close()
    return 0


def cmd_tree(args: argparse.Namespace) -> int:
    """Display the directory tree inside an E01 image."""
    if not _NATIVE_BACKEND:
        print(
            "[ERROR] 'tree' requires pyewf and pytsk3.\n"
            "Install them with: pip install pyewf pytsk3",
            file=sys.stderr,
        )
        return 1

    path = args.path or "/"
    max_depth = args.max_depth if args.max_depth is not None else -1

    try:
        img_info, fs_info = _open_fs(args.image)
    except Exception as exc:
        print(f"[ERROR] Could not open filesystem: {exc}", file=sys.stderr)
        return 1

    print(path)
    for depth, is_dir, full_path in _walk_dir(fs_info, path, max_depth):
        name = os.path.basename(full_path)
        indent = "    " * depth + ("📁 " if is_dir else "📄 ")
        print(f"{indent}{name}")

    img_info.close()
    return 0


def cmd_cat(args: argparse.Namespace) -> int:
    """Write the contents of a file inside an E01 image to stdout."""
    if not _NATIVE_BACKEND:
        print(
            "[ERROR] 'cat' requires pyewf and pytsk3.\n"
            "Install them with: pip install pyewf pytsk3",
            file=sys.stderr,
        )
        return 1

    try:
        img_info, fs_info = _open_fs(args.image)
    except Exception as exc:
        print(f"[ERROR] Could not open filesystem: {exc}", file=sys.stderr)
        return 1

    try:
        f = fs_info.open(path=args.internal_path)
    except Exception as exc:
        print(
            f"[ERROR] Could not open '{args.internal_path}': {exc}",
            file=sys.stderr,
        )
        img_info.close()
        return 1

    size = f.info.meta.size
    offset = 0
    CHUNK = 1024 * 1024  # 1 MiB
    stdout_bin = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout
    while offset < size:
        available = min(CHUNK, size - offset)
        data = f.read_random(offset, available)
        if not data:
            break
        stdout_bin.write(data)
        offset += len(data)

    img_info.close()
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract a file from an E01 image to the local filesystem."""
    if not _NATIVE_BACKEND:
        print(
            "[ERROR] 'extract' requires pyewf and pytsk3.\n"
            "Install them with: pip install pyewf pytsk3",
            file=sys.stderr,
        )
        return 1

    try:
        img_info, fs_info = _open_fs(args.image)
    except Exception as exc:
        print(f"[ERROR] Could not open filesystem: {exc}", file=sys.stderr)
        return 1

    src_path = args.internal_path
    dest_path = args.output or os.path.basename(src_path.rstrip("/"))

    try:
        entry = fs_info.open(path=src_path)
    except Exception as exc:
        print(f"[ERROR] Could not open '{src_path}': {exc}", file=sys.stderr)
        img_info.close()
        return 1

    import pytsk3

    is_dir = (
        entry.info.meta is not None
        and entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR
    )

    if is_dir:
        _extract_dir(fs_info, src_path, dest_path)
    else:
        _extract_file(entry, dest_path)
        print(f"Extracted: {src_path} -> {dest_path}")

    img_info.close()
    return 0


def _extract_file(tsk_file, dest_path: str):
    """Write a single TSK file object to dest_path on the local filesystem."""
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    size = tsk_file.info.meta.size
    CHUNK = 1024 * 1024
    offset = 0
    with open(dest_path, "wb") as out:
        while offset < size:
            available = min(CHUNK, size - offset)
            data = tsk_file.read_random(offset, available)
            if not data:
                break
            out.write(data)
            offset += len(data)


def _extract_dir(fs_info, src_path: str, dest_path: str):
    """Recursively extract a directory from the E01 filesystem."""
    import pytsk3

    os.makedirs(dest_path, exist_ok=True)
    try:
        directory = fs_info.open_dir(path=src_path)
    except Exception as exc:
        print(f"[WARN] Could not open '{src_path}': {exc}", file=sys.stderr)
        return

    for entry in directory:
        name = entry.info.name.name
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if name in (".", ".."):
            continue
        child_src = src_path.rstrip("/") + "/" + name
        child_dest = os.path.join(dest_path, name)
        is_dir = (
            entry.info.meta is not None
            and entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR
        )
        if is_dir:
            _extract_dir(fs_info, child_src, child_dest)
        else:
            try:
                child_file = fs_info.open(path=child_src)
                _extract_file(child_file, child_dest)
                print(f"Extracted: {child_src} -> {child_dest}")
            except Exception as exc:
                print(f"[WARN] Skipping '{child_src}': {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _add_image_arg(parser: argparse.ArgumentParser):
    parser.add_argument(
        "image",
        nargs="+",
        metavar="IMAGE",
        help="Path to the E01/EWF image file(s). "
        "For multi-segment images list all segments or just the first one.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="read_e01.py",
        description=(
            "Browse and extract files from E01/EWF forensic images.\n\n"
            f"Backend: {'pyewf + pytsk3 (full filesystem access)' if _NATIVE_BACKEND else 'ewfinfo/ewfexport fallback (install pyewf + pytsk3 for full access)'}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # info
    p_info = sub.add_parser("info", help="Show E01 metadata and case info.")
    _add_image_arg(p_info)
    p_info.set_defaults(func=cmd_info)

    # ls
    p_ls = sub.add_parser("ls", help="List directory contents inside the E01.")
    _add_image_arg(p_ls)
    p_ls.add_argument(
        "path",
        nargs="?",
        metavar="PATH",
        default="/",
        help="Directory path inside the image (default: /).",
    )
    p_ls.set_defaults(func=cmd_ls)

    # tree
    p_tree = sub.add_parser("tree", help="Show the directory tree inside the E01.")
    _add_image_arg(p_tree)
    p_tree.add_argument(
        "path",
        nargs="?",
        metavar="PATH",
        default="/",
        help="Root path for the tree (default: /).",
    )
    p_tree.add_argument(
        "--max-depth",
        type=int,
        metavar="N",
        default=None,
        help="Maximum directory depth to traverse (default: unlimited).",
    )
    p_tree.set_defaults(func=cmd_tree)

    # cat
    p_cat = sub.add_parser(
        "cat", help="Write a file from the E01 image to stdout."
    )
    _add_image_arg(p_cat)
    p_cat.add_argument(
        "internal_path",
        metavar="INTERNAL_PATH",
        help="Full path of the file inside the image (e.g. /Windows/System32/drivers/etc/hosts).",
    )
    p_cat.set_defaults(func=cmd_cat)

    # extract
    p_ext = sub.add_parser(
        "extract", help="Extract a file or directory from the E01 image."
    )
    _add_image_arg(p_ext)
    p_ext.add_argument(
        "internal_path",
        metavar="INTERNAL_PATH",
        help="Path of the file or directory inside the image to extract.",
    )
    p_ext.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT",
        help="Local path to write the extracted content to. "
        "Defaults to the basename of INTERNAL_PATH.",
    )
    p_ext.set_defaults(func=cmd_extract)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
