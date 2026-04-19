#!/usr/bin/env python3
"""
read_e01.py - Read and explore E01 forensic images.

Detects partition tables, identifies filesystems (NTFS, EXT2/3/4,
FAT12/16/32, …) and lets you list, tree, cat and extract files.

Usage:
  python3 read_e01.py info   <image.E01>
  python3 read_e01.py ls     <image.E01> [path]  [-p partition]
  python3 read_e01.py tree   <image.E01> [path]  [-p partition]
  python3 read_e01.py cat    <image.E01> <path>  [-p partition]
  python3 read_e01.py extract <image.E01> <path> [dest] [-p partition]

Requirements (install once):
  sudo apt-get install python3-libewf python3-tsk ewf-tools
"""

import argparse
import datetime
import os
import sys

try:
    import pyewf
except ImportError:
    sys.exit(
        "Error: pyewf not found.\n"
        "Install with:  sudo apt-get install python3-libewf"
    )

try:
    import pytsk3
except ImportError:
    sys.exit(
        "Error: pytsk3 not found.\n"
        "Install with:  sudo apt-get install python3-tsk"
    )


# ---------------------------------------------------------------------------
# EWF → pytsk3 bridge
# ---------------------------------------------------------------------------

class EWFImgInfo(pytsk3.Img_Info):
    """Thin bridge that lets pytsk3 read raw sectors from a pyewf handle."""

    def __init__(self, ewf_handle):
        self._ewf_handle = ewf_handle
        super().__init__(url="")

    def close(self):
        self._ewf_handle.close()

    def read(self, offset, size):
        self._ewf_handle.seek(offset)
        return self._ewf_handle.read(size)

    def get_size(self):
        return self._ewf_handle.get_media_size()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FS_TYPE_NAMES = {
    int(pytsk3.TSK_FS_TYPE_FAT12):   "FAT12",
    int(pytsk3.TSK_FS_TYPE_FAT16):   "FAT16",
    int(pytsk3.TSK_FS_TYPE_FAT32):   "FAT32",
    int(pytsk3.TSK_FS_TYPE_EXFAT):   "exFAT",
    int(pytsk3.TSK_FS_TYPE_NTFS):    "NTFS",
    int(pytsk3.TSK_FS_TYPE_EXT2):    "EXT2",
    int(pytsk3.TSK_FS_TYPE_EXT3):    "EXT3",
    int(pytsk3.TSK_FS_TYPE_EXT4):    "EXT4",
    int(pytsk3.TSK_FS_TYPE_ISO9660): "ISO9660",
    int(pytsk3.TSK_FS_TYPE_HFS):     "HFS",
    int(pytsk3.TSK_FS_TYPE_FFS1):    "UFS1",
    int(pytsk3.TSK_FS_TYPE_FFS2):    "UFS2",
    int(pytsk3.TSK_FS_TYPE_APFS):    "APFS",
    int(pytsk3.TSK_FS_TYPE_YAFFS2):  "YAFFS2",
}


def _fs_type_name(ftype):
    return FS_TYPE_NAMES.get(int(ftype), f"Unknown ({ftype})")


def _open_ewf(e01_path):
    """Open an E01 file (or multi-segment set) and return a pyewf handle."""
    if not os.path.exists(e01_path):
        sys.exit(f"Error: File not found: {e01_path}")
    try:
        filenames = pyewf.glob(e01_path)
    except Exception as exc:
        sys.exit(f"Error: Could not find EWF segments for '{e01_path}': {exc}")
    if not filenames:
        sys.exit(f"Error: No EWF files found matching: {e01_path}")
    handle = pyewf.handle()
    handle.open(filenames)
    return handle


def _get_filesystems(img):
    """Return a list of dicts describing every detectable filesystem.

    Each dict has keys:
      offset     – byte offset within the image
      fs         – pytsk3.FS_Info object
      desc       – human-readable description (from partition table or generic)
    """
    filesystems = []

    # Try to parse a volume/partition table first.
    try:
        volume = pytsk3.Volume_Info(img)
        for part in volume:
            if part.flags != pytsk3.TSK_VS_PART_FLAG_ALLOC:
                continue
            offset = part.start * volume.info.block_size
            try:
                fs = pytsk3.FS_Info(img, offset=offset)
                filesystems.append({
                    "offset": offset,
                    "fs": fs,
                    "desc": part.desc.decode("utf-8", errors="replace"),
                })
            except IOError:
                pass
    except IOError:
        # No recognisable partition table – try the image as a bare filesystem.
        try:
            fs = pytsk3.FS_Info(img)
            filesystems.append({
                "offset": 0,
                "fs": fs,
                "desc": "Raw filesystem (no partition table)",
            })
        except IOError:
            pass

    return filesystems


def _select_fs(ewf_handle, partition_index):
    """Return the pytsk3.FS_Info at *partition_index* (0-based)."""
    img = EWFImgInfo(ewf_handle)
    filesystems = _get_filesystems(img)
    if not filesystems:
        sys.exit("No filesystems detected in the image.")
    if partition_index >= len(filesystems):
        sys.exit(
            f"Partition index {partition_index} out of range "
            f"(found {len(filesystems)} filesystem(s))."
        )
    return filesystems[partition_index]["fs"]


def _iter_dir(fs, path, recursive=False, level=0):
    """Yield (level, is_dir, name, size, mtime_str) for every entry in *path*."""
    try:
        directory = fs.open_dir(path=path)
    except IOError as exc:
        print(f"Error opening '{path}': {exc}", file=sys.stderr)
        return

    for entry in directory:
        try:
            name = entry.info.name.name.decode("utf-8", errors="replace")
        except AttributeError:
            continue
        if name in (".", ".."):
            continue

        try:
            is_dir = entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR
            size   = entry.info.meta.size
            mtime  = entry.info.meta.mtime
        except AttributeError:
            is_dir, size, mtime = False, 0, 0

        try:
            mtime_str = (
                datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                if mtime else "-"
            )
        except (OSError, ValueError):
            mtime_str = "-"

        yield (level, is_dir, name, size, mtime_str)

        if recursive and is_dir:
            child_path = path.rstrip("/") + "/" + name
            yield from _iter_dir(fs, child_path, recursive=True, level=level + 1)


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_info(args):
    """Print EWF metadata + detected filesystems."""
    ewf_handle = _open_ewf(args.image)
    try:
        print("=== EWF Image Info ===")
        print(f"File:         {args.image}")

        media_size = ewf_handle.get_media_size()
        print(f"Media size:   {media_size:,} bytes ({media_size / (1024 ** 3):.2f} GB)")

        # Optional EWF header values (not always present)
        for key in ("case_number", "description", "examiner_name",
                    "evidence_number", "notes"):
            try:
                val = ewf_handle.get_header_value(key)
                if val:
                    print(f"{key.replace('_', ' ').title():14}{val}")
            except Exception:
                pass

        try:
            md5 = ewf_handle.get_hash_value("MD5")
            if md5:
                print(f"MD5:          {md5}")
        except Exception:
            pass

        img = EWFImgInfo(ewf_handle)
        filesystems = _get_filesystems(img)

        if not filesystems:
            print("\nNo filesystems detected.")
        else:
            print(f"\n=== Filesystems ({len(filesystems)} found) ===")
            for i, info in enumerate(filesystems):
                fs    = info["fs"]
                total = fs.info.block_size * fs.info.block_count
                print(f"\n[{i}] {info['desc']}")
                print(f"    Offset:      {info['offset']:,} bytes")
                print(f"    Type:        {_fs_type_name(fs.info.ftype)}")
                print(f"    Block size:  {fs.info.block_size} bytes")
                print(f"    Block count: {fs.info.block_count:,}")
                print(f"    Total size:  {total:,} bytes ({total / (1024 ** 2):.1f} MB)")
    finally:
        ewf_handle.close()


def cmd_ls(args):
    """List the contents of a directory inside the image."""
    ewf_handle = _open_ewf(args.image)
    try:
        fs   = _select_fs(ewf_handle, args.partition)
        path = args.path or "/"

        print(f"{'Type':<5}  {'Size':>12}  {'Modified':<19}  Name")
        print("-" * 64)
        for _, is_dir, name, size, mtime in _iter_dir(fs, path):
            type_str = "DIR " if is_dir else "FILE"
            size_str = "       -" if is_dir else f"{size:>12,}"
            print(f"{type_str:<5}  {size_str}  {mtime:<19}  {name}")
    finally:
        ewf_handle.close()


def cmd_tree(args):
    """Print a recursive directory tree."""
    ewf_handle = _open_ewf(args.image)
    try:
        fs   = _select_fs(ewf_handle, args.partition)
        path = (args.path or "/").rstrip("/") or "/"

        print(path)
        for level, is_dir, name, size, _ in _iter_dir(fs, path, recursive=True):
            indent  = "    " * level
            marker  = "└── "
            suffix  = "/" if is_dir else f"  ({size:,} bytes)"
            print(f"{indent}{marker}{name}{suffix}")
    finally:
        ewf_handle.close()


def cmd_cat(args):
    """Write a file's raw bytes to stdout."""
    ewf_handle = _open_ewf(args.image)
    try:
        fs = _select_fs(ewf_handle, args.partition)
        try:
            f = fs.open(args.path)
        except IOError as exc:
            sys.exit(f"Error opening '{args.path}': {exc}")

        size   = f.info.meta.size
        offset = 0
        chunk  = 1024 * 1024  # 1 MB
        while offset < size:
            to_read = min(chunk, size - offset)
            data    = f.read_random(offset, to_read)
            if not data:
                break
            sys.stdout.buffer.write(data)
            offset += len(data)
    finally:
        ewf_handle.close()


def cmd_extract(args):
    """Extract a file from the image to the local filesystem."""
    ewf_handle = _open_ewf(args.image)
    try:
        fs = _select_fs(ewf_handle, args.partition)
        try:
            f = fs.open(args.path)
        except IOError as exc:
            sys.exit(f"Error opening '{args.path}': {exc}")

        dest = args.dest or os.path.basename(args.path.rstrip("/"))
        size = f.info.meta.size
        offset, chunk, extracted = 0, 1024 * 1024, 0

        with open(dest, "wb") as out:
            while offset < size:
                to_read = min(chunk, size - offset)
                data    = f.read_random(offset, to_read)
                if not data:
                    break
                out.write(data)
                offset    += len(data)
                extracted += len(data)

        print(f"Extracted '{args.path}' → '{dest}' ({extracted:,} bytes)")
    finally:
        ewf_handle.close()


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Read and explore E01 forensic images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python3 read_e01.py info    image.E01
  python3 read_e01.py ls      image.E01 /documents
  python3 read_e01.py tree    image.E01
  python3 read_e01.py cat     image.E01 /documents/report.txt
  python3 read_e01.py extract image.E01 /documents/report.txt report.txt
  python3 read_e01.py ls      image.E01 / --partition 1
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # info
    p = sub.add_parser("info", help="Display image metadata and filesystem info")
    p.add_argument("image", help="Path to the E01 image (or first segment)")

    # ls
    p = sub.add_parser("ls", help="List files in a directory")
    p.add_argument("image", help="Path to the E01 image (or first segment)")
    p.add_argument("path", nargs="?", default="/",
                   help="Directory path inside the image (default: /)")
    p.add_argument("-p", "--partition", type=int, default=0, metavar="N",
                   help="Partition/filesystem index, 0-based (default: 0)")

    # tree
    p = sub.add_parser("tree", help="Display a recursive directory tree")
    p.add_argument("image", help="Path to the E01 image (or first segment)")
    p.add_argument("path", nargs="?", default="/",
                   help="Root path for the tree (default: /)")
    p.add_argument("-p", "--partition", type=int, default=0, metavar="N",
                   help="Partition/filesystem index, 0-based (default: 0)")

    # cat
    p = sub.add_parser("cat", help="Print a file's contents to stdout")
    p.add_argument("image", help="Path to the E01 image (or first segment)")
    p.add_argument("path", help="File path inside the image")
    p.add_argument("-p", "--partition", type=int, default=0, metavar="N",
                   help="Partition/filesystem index, 0-based (default: 0)")

    # extract
    p = sub.add_parser("extract", help="Extract a file from the image")
    p.add_argument("image", help="Path to the E01 image (or first segment)")
    p.add_argument("path", help="File path inside the image")
    p.add_argument("dest", nargs="?", default=None,
                   help="Destination path (default: basename of source)")
    p.add_argument("-p", "--partition", type=int, default=0, metavar="N",
                   help="Partition/filesystem index, 0-based (default: 0)")

    args = parser.parse_args()
    {
        "info":    cmd_info,
        "ls":      cmd_ls,
        "tree":    cmd_tree,
        "cat":     cmd_cat,
        "extract": cmd_extract,
    }[args.command](args)


if __name__ == "__main__":
    main()
