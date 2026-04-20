#!/usr/bin/env python3
"""
ewf_tools.py - Comprehensive E01 forensic image management utility.

Wraps the libewf command-line tools (ewfinfo, ewfacquire, ewfacquirestream,
ewfexport, ewfverify, ewfrecover, ewfmount, ewfdebug) to provide a unified
interface for creating, reading, exporting and verifying E01/EWF images.

The repository bundles Windows libewf executables under ewf/.
On Windows they are executed directly. On Linux/macOS the script prefers
native tools in PATH and can fall back to the bundled .exe files via Wine.

Usage:
    python ewf_tools.py <command> [options]

Commands:
    info            Display metadata / case information for an E01 image.
    acquire         Create an E01 image from a physical disk or device.
    acquire-stream  Create an E01 image from a raw data stream (stdin / pipe).
    export          Export an E01 image to raw (dd), another E01, or other formats.
    verify          Verify the integrity (MD5/SHA1 checksums) of an E01 image.
    recover         Recover a corrupted or incomplete E01 image.
    mount           Mount an E01 image as a virtual filesystem (Linux only).
    debug           Display low-level debug information for an E01 image.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_EWF_DIR = os.path.join(_SCRIPT_DIR, "ewf")
_MOUNT_REGISTRY = os.path.join(_SCRIPT_DIR, ".ewf_mounts.json")

# Map logical tool name -> executable stem
_TOOLS = {
    "ewfinfo": "ewfinfo",
    "ewfacquire": "ewfacquire",
    "ewfacquirestream": "ewfacquirestream",
    "ewfexport": "ewfexport",
    "ewfverify": "ewfverify",
    "ewfrecover": "ewfrecover",
    "ewfmount": "ewfmount",
    "ewfdebug": "ewfdebug",
}


def _resolve_tool_command(name: str) -> list[str]:
    """Return the command used to execute a libewf tool.

    Search order:
    1. Native tool in PATH (works on Linux/macOS with libewf installed).
    2. Bundled .exe in the ewf/ subdirectory.
       On Linux/macOS Wine is required to run the bundled Windows binaries.
    """
    native = shutil.which(name)
    if native:
        return [native]

    exe_name = name + ".exe"
    bundled = os.path.join(_EWF_DIR, exe_name)
    if os.path.isfile(bundled):
        if platform.system() == "Windows":
            return [bundled]

        wine = shutil.which("wine")
        if wine:
            return [wine, bundled]

        print(
            f"[ERROR] Found bundled Windows executable '{exe_name}' in '{_EWF_DIR}',\n"
            "but Wine is not installed. On Linux/macOS either install native\n"
            "libewf tools (e.g. 'sudo apt-get install ewf-tools') or install Wine\n"
            "to run the bundled executables.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"[ERROR] '{name}' not found in PATH or '{_EWF_DIR}'.\n"
        "Install libewf (e.g. 'sudo apt-get install ewf-tools') or ensure "
        f"the bundled '{exe_name}' is present in the ewf/ directory.",
        file=sys.stderr,
    )
    sys.exit(1)


def _run(args: list, stdin=None, check: bool = False) -> int:
    """Execute a tool and stream its output to stdout/stderr.

    Returns the process exit code.
    """
    try:
        result = subprocess.run(args, stdin=stdin)
    except FileNotFoundError:
        print(f"[ERROR] Could not execute: {args[0]}", file=sys.stderr)
        sys.exit(1)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def _load_mount_registry() -> list[dict]:
    if not os.path.exists(_MOUNT_REGISTRY):
        return []
    try:
        with open(_MOUNT_REGISTRY, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_mount_registry(entries: list[dict]) -> None:
    with open(_MOUNT_REGISTRY, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)


def _read_system_mount_points() -> set[str]:
    mount_points = set()
    if platform.system() == "Linux" and os.path.exists("/proc/mounts"):
        try:
            with open("/proc/mounts", "r", encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) >= 2:
                        mount_points.add(parts[1].replace("\\040", " "))
        except OSError:
            pass
        return mount_points

    mount_cmd = shutil.which("mount")
    if not mount_cmd:
        return mount_points

    result = subprocess.run([mount_cmd], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if " on " in line:
            try:
                mount_points.add(line.split(" on ", 1)[1].split(" ", 1)[0])
            except IndexError:
                continue
    return mount_points


def _is_mounted(mount_point: str) -> bool:
    return os.path.abspath(mount_point) in {
        os.path.abspath(path) for path in _read_system_mount_points()
    }


def _record_mount(images: list[str], mount_point: str) -> None:
    entries = _load_mount_registry()
    mount_point = os.path.abspath(mount_point)
    now = datetime.now(timezone.utc).isoformat()
    updated = False
    for entry in entries:
        if os.path.abspath(entry.get("mount_point", "")) == mount_point:
            entry["images"] = [str(image) for image in images]
            entry["mounted_at"] = now
            updated = True
            break
    if not updated:
        entries.append(
            {
                "mount_point": mount_point,
                "images": [str(image) for image in images],
                "mounted_at": now,
            }
        )
    _save_mount_registry(entries)


def _remove_mount(mount_point: str) -> bool:
    mount_point = os.path.abspath(mount_point)
    entries = _load_mount_registry()
    filtered = [
        entry
        for entry in entries
        if os.path.abspath(entry.get("mount_point", "")) != mount_point
    ]
    changed = len(filtered) != len(entries)
    if changed:
        _save_mount_registry(filtered)
    return changed


def _list_mount_entries(include_stale: bool = False) -> list[dict]:
    entries = _load_mount_registry()
    system_mounts = {os.path.abspath(path) for path in _read_system_mount_points()}
    results = []
    for entry in entries:
        mount_point = os.path.abspath(entry.get("mount_point", ""))
        mounted = mount_point in system_mounts
        if include_stale or mounted:
            results.append(
                {
                    "mount_point": mount_point,
                    "images": entry.get("images", []),
                    "mounted_at": entry.get("mounted_at"),
                    "mounted": mounted,
                }
            )
    return results


def _resolve_unmount_command() -> list[str] | None:
    for tool, extra_args in (("fusermount3", ["-u"]), ("fusermount", ["-u"]), ("umount", [])):
        resolved = shutil.which(tool)
        if resolved:
            return [resolved] + extra_args
    return None


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------


def cmd_info(args: argparse.Namespace) -> int:
    """Display metadata / case information stored in an E01 image."""
    cmd = _resolve_tool_command("ewfinfo")
    if args.date_format:
        cmd += ["-d", args.date_format]
    if args.header_format:
        cmd += ["-f", args.header_format]
    if args.verbose:
        cmd.append("-v")
    cmd += args.image
    return _run(cmd)


def cmd_acquire(args: argparse.Namespace) -> int:
    """Acquire an E01 image from a physical disk or device."""
    cmd = _resolve_tool_command("ewfacquire")
    if args.format:
        cmd += ["-f", args.format]
    if args.target:
        cmd += ["-t", args.target]
    if args.segment_size:
        cmd += ["-S", args.segment_size]
    if args.compression:
        cmd += ["-c", args.compression]
    if args.bytes_per_sector:
        cmd += ["-b", str(args.bytes_per_sector)]
    if args.sectors_per_chunk:
        cmd += ["-s", str(args.sectors_per_chunk)]
    if args.case_number:
        cmd += ["-C", args.case_number]
    if args.description:
        cmd += ["-D", args.description]
    if args.evidence_number:
        cmd += ["-e", args.evidence_number]
    if args.examiner:
        cmd += ["-E", args.examiner]
    if args.notes:
        cmd += ["-N", args.notes]
    if args.media_type:
        cmd += ["-m", args.media_type]
    if args.media_flags:
        cmd += ["-M", args.media_flags]
    if args.hash:
        for h in args.hash:
            cmd += ["-d", h]
    if args.read_error_retry:
        cmd += ["-r", str(args.read_error_retry)]
    if args.resume:
        cmd.append("-R")
    if args.no_prompt:
        cmd.append("-u")
    if args.verbose:
        cmd.append("-v")
    cmd.append(args.source)
    return _run(cmd)


def cmd_acquire_stream(args: argparse.Namespace) -> int:
    """Create an E01 image by reading a raw data stream from stdin (or a file).

    This is the recommended way to wrap 'dd' or other raw-image tools:

        dd if=/dev/sda bs=512 | python ewf_tools.py acquire-stream -t output_image

    If --input is provided the file is opened and fed to ewfacquirestream as
    stdin instead of the process's own stdin.
    """
    cmd = _resolve_tool_command("ewfacquirestream")
    if args.format:
        cmd += ["-f", args.format]
    if args.target:
        cmd += ["-t", args.target]
    if args.segment_size:
        cmd += ["-S", args.segment_size]
    if args.compression:
        cmd += ["-c", args.compression]
    if args.bytes_per_sector:
        cmd += ["-b", str(args.bytes_per_sector)]
    if args.sectors_per_chunk:
        cmd += ["-s", str(args.sectors_per_chunk)]
    if args.case_number:
        cmd += ["-C", args.case_number]
    if args.description:
        cmd += ["-D", args.description]
    if args.evidence_number:
        cmd += ["-e", args.evidence_number]
    if args.examiner:
        cmd += ["-E", args.examiner]
    if args.notes:
        cmd += ["-N", args.notes]
    if args.media_type:
        cmd += ["-m", args.media_type]
    if args.hash:
        for h in args.hash:
            cmd += ["-d", h]
    if args.no_prompt:
        cmd.append("-u")
    if args.verbose:
        cmd.append("-v")

    if args.input:
        with open(args.input, "rb") as fh:
            return _run(cmd, stdin=fh)
    else:
        return _run(cmd, stdin=sys.stdin.buffer)


def cmd_export(args: argparse.Namespace) -> int:
    """Export an E01 image to a raw (dd) file, another E01, or other formats."""
    cmd = _resolve_tool_command("ewfexport")
    if args.format:
        cmd += ["-f", args.format]
    if args.target:
        cmd += ["-t", args.target]
    if args.segment_size:
        cmd += ["-S", args.segment_size]
    if args.compression:
        cmd += ["-c", args.compression]
    if args.offset:
        cmd += ["-o", str(args.offset)]
    if args.size:
        cmd += ["-s", str(args.size)]
    if args.hash:
        for h in args.hash:
            cmd += ["-d", h]
    if args.no_prompt:
        cmd.append("-u")
    if args.verbose:
        cmd.append("-v")
    cmd += args.image
    return _run(cmd)


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify the integrity (MD5/SHA1 checksums) of an E01 image."""
    cmd = _resolve_tool_command("ewfverify")
    if args.hash:
        for h in args.hash:
            cmd += ["-d", h]
    if args.verbose:
        cmd.append("-v")
    cmd += args.image
    return _run(cmd)


def cmd_recover(args: argparse.Namespace) -> int:
    """Attempt to recover data from a corrupted or incomplete E01 image."""
    cmd = _resolve_tool_command("ewfrecover")
    if args.target:
        cmd += ["-t", args.target]
    if args.verbose:
        cmd.append("-v")
    cmd += args.image
    return _run(cmd)


def cmd_mount(args: argparse.Namespace) -> int:
    """Mount an E01 image as a virtual filesystem (Linux only).

    The image is exposed as a block device under the mount point so that
    standard filesystem tools (mount, file, etc.) can be used on it.
    """
    if platform.system() == "Windows":
        print(
            "[ERROR] 'mount' is not supported on Windows. "
            "Use Arsenal Image Mounter or FTK Imager instead.",
            file=sys.stderr,
        )
        return 1
    cmd = _resolve_tool_command("ewfmount")
    if args.verbose:
        cmd.append("-v")
    cmd += args.image
    cmd.append(args.mount_point)
    os.makedirs(args.mount_point, exist_ok=True)
    exit_code = _run(cmd)
    if exit_code == 0:
        _record_mount(args.image, args.mount_point)
    return exit_code


def cmd_unmount(args: argparse.Namespace) -> int:
    """Unmount a previously mounted E01 image mount point."""
    if platform.system() == "Windows":
        print("[ERROR] 'unmount' is not supported on Windows.", file=sys.stderr)
        return 1

    unmount_cmd = _resolve_unmount_command()
    if unmount_cmd is None:
        print(
            "[ERROR] No unmount command available. Install fusermount/fusermount3 or use umount.",
            file=sys.stderr,
        )
        return 1

    exit_code = _run(unmount_cmd + [args.mount_point])
    if exit_code == 0:
        _remove_mount(args.mount_point)
    return exit_code


def cmd_mounts(args: argparse.Namespace) -> int:
    """List known E01 mount points tracked by this utility."""
    print(json.dumps({"mounts": _list_mount_entries(include_stale=args.all)}, indent=2))
    return 0


def cmd_debug(args: argparse.Namespace) -> int:
    """Display low-level debug / internal structure information for an E01 image."""
    cmd = _resolve_tool_command("ewfdebug")
    if args.verbose:
        cmd.append("-v")
    cmd += args.image
    return _run(cmd)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _add_common_image_arg(parser: argparse.ArgumentParser, nargs="+"):
    parser.add_argument(
        "image",
        nargs=nargs,
        metavar="IMAGE",
        help="Path to the E01/EWF image file(s). "
        "For multi-segment images list all segments or just the first one.",
    )


def _add_verbose(parser: argparse.ArgumentParser):
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output.")


def _add_hash_option(parser: argparse.ArgumentParser):
    parser.add_argument(
        "-d",
        "--hash",
        action="append",
        metavar="TYPE",
        help="Digest (hash) type to calculate: md5, sha1, sha256. "
        "Can be specified multiple times.",
    )


def _add_no_prompt(parser: argparse.ArgumentParser):
    parser.add_argument(
        "-u",
        "--no-prompt",
        action="store_true",
        help="Unattended mode - do not prompt for user input.",
    )


def _add_acquire_options(parser: argparse.ArgumentParser):
    parser.add_argument(
        "-f",
        "--format",
        metavar="FORMAT",
        help="Output format: ewf (default), encase1-7, smart, ftk, linen5-7, ewfx.",
    )
    parser.add_argument(
        "-t",
        "--target",
        metavar="TARGET",
        help="Base name (without extension) for the output image files.",
    )
    parser.add_argument(
        "-S",
        "--segment-size",
        metavar="SIZE",
        help="Maximum segment file size (e.g. 650MB, 2GB, 5000000000).",
    )
    parser.add_argument(
        "-c",
        "--compression",
        metavar="TYPE",
        help="Compression type: none (default), empty-block, fast, best.",
    )
    parser.add_argument(
        "-b",
        "--bytes-per-sector",
        type=int,
        metavar="N",
        help="Number of bytes per sector (default: 512).",
    )
    parser.add_argument(
        "-s",
        "--sectors-per-chunk",
        type=int,
        metavar="N",
        help="Number of sectors per chunk (default: 64).",
    )
    parser.add_argument("-C", "--case-number", metavar="NUMBER", help="Case number.")
    parser.add_argument(
        "-D", "--description", metavar="TEXT", help="Evidence description."
    )
    parser.add_argument(
        "-e", "--evidence-number", metavar="NUMBER", help="Evidence number."
    )
    parser.add_argument("-E", "--examiner", metavar="NAME", help="Examiner name.")
    parser.add_argument("-N", "--notes", metavar="TEXT", help="Notes.")
    parser.add_argument(
        "-m",
        "--media-type",
        metavar="TYPE",
        help="Media type: fixed (default), removable, optical, memory.",
    )
    parser.add_argument(
        "-M",
        "--media-flags",
        metavar="FLAGS",
        help="Media flags: logical, physical (default).",
    )
    _add_hash_option(parser)
    _add_verbose(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ewf_tools.py",
        description=(
            "Comprehensive E01/EWF forensic image management utility.\n"
            "Wraps ewfinfo, ewfacquire, ewfacquirestream, ewfexport, "
            "ewfverify, ewfrecover, ewfmount and ewfdebug."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # -- info -----------------------------------------------------------------
    p_info = sub.add_parser("info", help="Show E01 image metadata and case info.")
    _add_common_image_arg(p_info)
    p_info.add_argument(
        "-d",
        "--date-format",
        metavar="FORMAT",
        help="Date format: ctime (default), dm, md, iso8601.",
    )
    p_info.add_argument(
        "-f",
        "--header-format",
        metavar="FORMAT",
        help="Header value format: text (default), html.",
    )
    _add_verbose(p_info)
    p_info.set_defaults(func=cmd_info)

    # -- acquire --------------------------------------------------------------
    p_acq = sub.add_parser(
        "acquire",
        help="Create an E01 image from a physical disk or device.",
        description=(
            "Acquire a forensic E01 image directly from a disk or device.\n\n"
            "Example:\n"
            "  python ewf_tools.py acquire -t evidence -C 2024-001 "
            "-E 'J. Smith' /dev/sdb"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_acq.add_argument("source", metavar="SOURCE", help="Source disk or device path.")
    _add_acquire_options(p_acq)
    p_acq.add_argument(
        "-r",
        "--read-error-retry",
        type=int,
        metavar="N",
        help="Number of retries on read error (default: 2).",
    )
    p_acq.add_argument(
        "-R",
        "--resume",
        action="store_true",
        help="Resume a previously interrupted acquisition.",
    )
    _add_no_prompt(p_acq)
    p_acq.set_defaults(func=cmd_acquire)

    # -- acquire-stream -------------------------------------------------------
    p_stream = sub.add_parser(
        "acquire-stream",
        help="Create an E01 image from a raw data stream (stdin or file).",
        description=(
            "Create an E01 image by reading raw data from stdin or an input file.\n\n"
            "Examples:\n"
            "  # Pipe dd output directly into an E01:\n"
            "  dd if=/dev/sda bs=512 | python ewf_tools.py acquire-stream "
            "-t evidence\n\n"
            "  # Convert an existing raw (dd) image to E01:\n"
            "  python ewf_tools.py acquire-stream -i disk.raw -t evidence"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_stream.add_argument(
        "-i",
        "--input",
        metavar="FILE",
        help="Raw image file to read instead of stdin "
        "(e.g. a .raw, .dd, .img file).",
    )
    _add_acquire_options(p_stream)
    _add_no_prompt(p_stream)
    p_stream.set_defaults(func=cmd_acquire_stream)

    # -- export ---------------------------------------------------------------
    p_exp = sub.add_parser(
        "export",
        help="Export an E01 image to raw (dd) or another format.",
        description=(
            "Export an existing E01 image to a raw image, another E01, or other\n"
            "supported output formats.\n\n"
            "Examples:\n"
            "  # Export E01 to a raw image:\n"
            "  python ewf_tools.py export -f raw -t output evidence.E01\n\n"
            "  # Export E01 to another E01 with best compression:\n"
            "  python ewf_tools.py export -f ewf -c best -t compressed evidence.E01"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_image_arg(p_exp)
    p_exp.add_argument(
        "-f",
        "--format",
        metavar="FORMAT",
        help="Output format: raw (default), ewf, encase1-7, smart, ftk, linen5-7.",
    )
    p_exp.add_argument(
        "-t",
        "--target",
        metavar="TARGET",
        help="Base name for the output file(s).",
    )
    p_exp.add_argument(
        "-S",
        "--segment-size",
        metavar="SIZE",
        help="Maximum segment file size.",
    )
    p_exp.add_argument(
        "-c",
        "--compression",
        metavar="TYPE",
        help="Compression type: none, empty-block, fast, best.",
    )
    p_exp.add_argument(
        "-o",
        "--offset",
        type=int,
        metavar="OFFSET",
        help="Start offset (in bytes) within the image to export.",
    )
    p_exp.add_argument(
        "-s",
        "--size",
        type=int,
        metavar="SIZE",
        help="Number of bytes to export.",
    )
    _add_hash_option(p_exp)
    _add_no_prompt(p_exp)
    _add_verbose(p_exp)
    p_exp.set_defaults(func=cmd_export)

    # -- verify ---------------------------------------------------------------
    p_ver = sub.add_parser(
        "verify",
        help="Verify the integrity (checksums) of an E01 image.",
        description=(
            "Verify the stored MD5/SHA1 checksums against the image data.\n\n"
            "Example:\n"
            "  python ewf_tools.py verify evidence.E01"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_image_arg(p_ver)
    _add_hash_option(p_ver)
    _add_verbose(p_ver)
    p_ver.set_defaults(func=cmd_verify)

    # -- recover --------------------------------------------------------------
    p_rec = sub.add_parser(
        "recover",
        help="Recover data from a corrupted or incomplete E01 image.",
        description=(
            "Attempt to recover data from a damaged or incomplete E01 image.\n\n"
            "Example:\n"
            "  python ewf_tools.py recover -t recovered corrupted.E01"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_image_arg(p_rec)
    p_rec.add_argument(
        "-t",
        "--target",
        metavar="TARGET",
        help="Base name for the recovered output image.",
    )
    _add_verbose(p_rec)
    p_rec.set_defaults(func=cmd_recover)

    # -- mount ----------------------------------------------------------------
    p_mnt = sub.add_parser(
        "mount",
        help="Mount an E01 image as a virtual filesystem (Linux only).",
        description=(
            "Mount an E01 image so that its contents are accessible as a\n"
            "regular filesystem.  Requires ewfmount and FUSE (Linux only).\n\n"
            "Example:\n"
            "  mkdir /mnt/evidence\n"
            "  python ewf_tools.py mount evidence.E01 /mnt/evidence\n"
            "  # When finished:\n"
            "  fusermount -u /mnt/evidence"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_image_arg(p_mnt)
    p_mnt.add_argument(
        "mount_point",
        metavar="MOUNT_POINT",
        help="Directory where the image will be mounted.",
    )
    _add_verbose(p_mnt)
    p_mnt.set_defaults(func=cmd_mount)

    # -- unmount --------------------------------------------------------------
    p_umnt = sub.add_parser(
        "unmount",
        help="Unmount a previously mounted E01 mount point.",
        description=(
            "Unmount an E01 image mount point created with ewfmount.\n\n"
            "Example:\n"
            "  python ewf_tools.py unmount /mnt/evidence"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_umnt.add_argument(
        "mount_point",
        metavar="MOUNT_POINT",
        help="Directory currently used as mount point.",
    )
    p_umnt.set_defaults(func=cmd_unmount)

    # -- mounts ---------------------------------------------------------------
    p_mounts = sub.add_parser(
        "mounts",
        help="List tracked E01 mount points.",
        description=(
            "List E01 mount points tracked by this utility and whether they are\n"
            "still mounted according to the operating system.\n\n"
            "Example:\n"
            "  python ewf_tools.py mounts --all"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_mounts.add_argument(
        "--all",
        action="store_true",
        help="Include stale registry entries that are no longer mounted.",
    )
    p_mounts.set_defaults(func=cmd_mounts)

    # -- debug ----------------------------------------------------------------
    p_dbg = sub.add_parser(
        "debug",
        help="Display low-level debug info for an E01 image.",
        description=(
            "Print the internal structure and low-level metadata of an E01 image.\n\n"
            "Example:\n"
            "  python ewf_tools.py debug evidence.E01"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_image_arg(p_dbg)
    _add_verbose(p_dbg)
    p_dbg.set_defaults(func=cmd_debug)

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
