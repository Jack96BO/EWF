#!/usr/bin/env python3
"""
ewf_tools.py - CLI wrapper for bundled EWF tools.

Subcommands:
  info            Display information about an E01 image
  acquire         Create an E01 image from a raw disk or image file
  acquire-stream  Create an E01 image by reading from stdin (or a file via --input)
  export          Export an E01 image to another format
  verify          Verify the integrity of an E01 image
  recover         Recover an E01 image
  mount           Mount an E01 image at a mount point
  debug           Display internal debug information for an E01 image

Bundled EWF tools are expected in the 'ewf/' subdirectory next to this script.
On Windows the bundled .exe files are used directly.
On Linux/macOS the bundled .exe files require Wine; as a fallback the script
will also search the system PATH for tools named without the .exe suffix
(e.g. 'ewfinfo' from the 'ewf-tools' package).

Examples:
  python ewf_tools.py info image.E01
  python ewf_tools.py acquire -f ewf -S 5000000000 -t /output/image source.001
  python ewf_tools.py acquire-stream --input source.raw -t /output/image
  python ewf_tools.py export -t /output/raw image.E01 image.E02
  python ewf_tools.py verify image.E01
  python ewf_tools.py mount image.E01 /mnt/ewf
"""

import argparse
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EWF_DIR = os.path.join(SCRIPT_DIR, "ewf")

# Map each subcommand to the underlying EWF tool name (without extension)
_TOOL_MAP = {
    "info": "ewfinfo",
    "acquire": "ewfacquire",
    "acquire-stream": "ewfacquirestream",
    "export": "ewfexport",
    "verify": "ewfverify",
    "recover": "ewfrecover",
    "mount": "ewfmount",
    "debug": "ewfdebug",
}


def find_tool(name: str) -> str | None:
    """Return the absolute path of an EWF tool.

    Search order:
    1. Bundled <name>.exe in the ewf/ directory.
    2. <name> (no extension) on the system PATH.
    """
    bundled = os.path.join(EWF_DIR, name + ".exe")
    if os.path.isfile(bundled):
        return bundled
    system = shutil.which(name)
    if system:
        return system
    return None


def run_tool(tool_name: str, extra_args: list[str]) -> None:
    """Locate *tool_name* and execute it with *extra_args*, then exit."""
    tool = find_tool(tool_name)
    if not tool:
        print(
            f"Error: '{tool_name}' not found in '{EWF_DIR}' or on PATH.\n"
            "On Linux install the 'ewf-tools' package or use Wine with the bundled executables.",
            file=sys.stderr,
        )
        sys.exit(1)

    cmd = [tool] + extra_args
    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except (FileNotFoundError, PermissionError, OSError):
        print(
            f"Error: cannot execute '{tool}'.\n"
            "On Linux, install Wine to run the bundled Windows executables, "
            "or install 'ewf-tools' for native Linux binaries.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_info(args: argparse.Namespace) -> None:
    run_tool(_TOOL_MAP["info"], args.images)


def cmd_acquire(args: argparse.Namespace) -> None:
    extra: list[str] = []
    if args.format:
        extra += ["-f", args.format]
    if args.segment_size:
        extra += ["-S", str(args.segment_size)]
    if args.target:
        extra += ["-t", args.target]
    extra.append(args.source)
    run_tool(_TOOL_MAP["acquire"], extra)


def cmd_acquire_stream(args: argparse.Namespace) -> None:
    tool = find_tool(_TOOL_MAP["acquire-stream"])
    if not tool:
        print(
            f"Error: '{_TOOL_MAP['acquire-stream']}' not found in '{EWF_DIR}' or on PATH.",
            file=sys.stderr,
        )
        sys.exit(1)

    extra: list[str] = []
    if args.target:
        extra += ["-t", args.target]

    cmd = [tool] + extra
    try:
        if args.input:
            with open(args.input, "rb") as fh:
                result = subprocess.run(cmd, stdin=fh, check=False)
        else:
            result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except (FileNotFoundError, PermissionError):
        print(
            f"Error: cannot execute '{tool}'.\n"
            "On Linux, install Wine to run the bundled Windows executables, "
            "or install 'ewf-tools' for native Linux binaries.",
            file=sys.stderr,
        )
        sys.exit(1)
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_export(args: argparse.Namespace) -> None:
    extra: list[str] = []
    if args.target:
        extra += ["-t", args.target]
    extra += args.images
    run_tool(_TOOL_MAP["export"], extra)


def cmd_verify(args: argparse.Namespace) -> None:
    run_tool(_TOOL_MAP["verify"], args.images)


def cmd_recover(args: argparse.Namespace) -> None:
    run_tool(_TOOL_MAP["recover"], args.images)


def cmd_mount(args: argparse.Namespace) -> None:
    run_tool(_TOOL_MAP["mount"], args.images + [args.mount_point])


def cmd_debug(args: argparse.Namespace) -> None:
    run_tool(_TOOL_MAP["debug"], args.images)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ewf_tools.py",
        description="CLI wrapper for EWF tools — manage Expert Witness Format (E01) images.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- info ----------------------------------------------------------------
    p_info = subparsers.add_parser(
        "info", help="Display information about an E01 image"
    )
    p_info.add_argument(
        "images", nargs="+", metavar="IMAGE", help="E01 image segment file(s)"
    )
    p_info.set_defaults(func=cmd_info)

    # -- acquire -------------------------------------------------------------
    p_acq = subparsers.add_parser(
        "acquire", help="Create an E01 image from a raw disk or image file"
    )
    p_acq.add_argument("source", metavar="SOURCE", help="Source file or device path")
    p_acq.add_argument(
        "-f", "--format", default="ewf", metavar="FORMAT",
        help="Output image format (default: ewf)",
    )
    p_acq.add_argument(
        "-S", "--segment-size", metavar="BYTES",
        help="Maximum segment file size in bytes (e.g. 5000000000)",
    )
    p_acq.add_argument(
        "-t", "--target", metavar="TARGET",
        help="Target base path for the output image (without extension)",
    )
    p_acq.set_defaults(func=cmd_acquire)

    # -- acquire-stream ------------------------------------------------------
    p_acs = subparsers.add_parser(
        "acquire-stream",
        help="Create an E01 image by reading raw data from stdin (or --input file)",
    )
    p_acs.add_argument(
        "-i", "--input", metavar="FILE",
        help="Read raw data from FILE instead of stdin",
    )
    p_acs.add_argument(
        "-t", "--target", metavar="TARGET",
        help="Target base path for the output image (without extension)",
    )
    p_acs.set_defaults(func=cmd_acquire_stream)

    # -- export --------------------------------------------------------------
    p_exp = subparsers.add_parser(
        "export", help="Export an E01 image to another format"
    )
    p_exp.add_argument(
        "images", nargs="+", metavar="IMAGE", help="E01 image segment file(s)"
    )
    p_exp.add_argument(
        "-t", "--target", metavar="TARGET",
        help="Target base path for the exported output",
    )
    p_exp.set_defaults(func=cmd_export)

    # -- verify --------------------------------------------------------------
    p_ver = subparsers.add_parser(
        "verify", help="Verify the integrity of an E01 image"
    )
    p_ver.add_argument(
        "images", nargs="+", metavar="IMAGE", help="E01 image segment file(s)"
    )
    p_ver.set_defaults(func=cmd_verify)

    # -- recover -------------------------------------------------------------
    p_rec = subparsers.add_parser(
        "recover", help="Recover an E01 image"
    )
    p_rec.add_argument(
        "images", nargs="+", metavar="IMAGE", help="E01 image segment file(s)"
    )
    p_rec.set_defaults(func=cmd_recover)

    # -- mount ---------------------------------------------------------------
    p_mnt = subparsers.add_parser(
        "mount", help="Mount an E01 image at a directory"
    )
    p_mnt.add_argument(
        "images", nargs="+", metavar="IMAGE", help="E01 image segment file(s)"
    )
    p_mnt.add_argument(
        "mount_point", metavar="MOUNT_POINT", help="Directory to mount the image at"
    )
    p_mnt.set_defaults(func=cmd_mount)

    # -- debug ---------------------------------------------------------------
    p_dbg = subparsers.add_parser(
        "debug", help="Display internal debug information for an E01 image"
    )
    p_dbg.add_argument(
        "images", nargs="+", metavar="IMAGE", help="E01 image segment file(s)"
    )
    p_dbg.set_defaults(func=cmd_debug)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
