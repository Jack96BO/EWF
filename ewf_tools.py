#!/usr/bin/env python3
"""
ewf_tools.py — CLI wrapper for the bundled EWF executables (ewf/ directory).

Usage:
  python ewf_tools.py info        <image.E01> [...]
  python ewf_tools.py acquire     -t <target> <source>
  python ewf_tools.py acquire-stream --input <raw_file> -t <target>
  python ewf_tools.py export      <image.E01> [...] -t <output>
  python ewf_tools.py verify      <image.E01> [...]
  python ewf_tools.py recover     <image.E01> [...] -t <output>
  python ewf_tools.py mount       <image.E01> [...] <mount_point>
  python ewf_tools.py debug       <image.E01> [...]

All extra arguments after the subcommand are forwarded directly to the
underlying executable.  Run with --help on any subcommand to see the
tool's own help text.

Examples:
  python ewf_tools.py info disk.E01
  python ewf_tools.py acquire -f ewf -S 5000000000 -t D:\\dest D:\\source\\image.001
  python ewf_tools.py acquire-stream --input raw.dd -t D:\\dest\\image
  python ewf_tools.py export disk.E01 -t D:\\dest\\exported
  python ewf_tools.py verify disk.E01
"""

import argparse
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Locate the ewf/ directory that sits next to this script
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EWF_DIR = os.path.join(SCRIPT_DIR, "ewf")

TOOL_MAP = {
    "info":           "ewfinfo.exe",
    "acquire":        "ewfacquire.exe",
    "acquire-stream": "ewfacquirestream.exe",
    "export":         "ewfexport.exe",
    "verify":         "ewfverify.exe",
    "recover":        "ewfrecover.exe",
    "mount":          "ewfmount.exe",
    "debug":          "ewfdebug.exe",
}


def resolve_tool(name: str) -> str:
    """Return the full path to an EWF executable, falling back to PATH."""
    local = os.path.join(EWF_DIR, name)
    if os.path.isfile(local):
        return local
    # Fall back to whatever is on PATH (Linux package installs, etc.)
    return name


def run_tool(subcommand: str, extra_args: list[str]) -> int:
    exe_name = TOOL_MAP[subcommand]
    exe_path = resolve_tool(exe_name)

    # Special handling: acquire-stream can accept a --input flag to pipe a
    # raw image file into ewfacquirestream via stdin.
    stdin_file = None
    if subcommand == "acquire-stream" and "--input" in extra_args:
        idx = extra_args.index("--input")
        input_path = extra_args[idx + 1]
        extra_args = extra_args[:idx] + extra_args[idx + 2:]
        stdin_file = open(input_path, "rb")  # noqa: WPS515 (open in branch)

    cmd = [exe_path] + extra_args
    try:
        result = subprocess.run(cmd, stdin=stdin_file)
        return result.returncode
    except FileNotFoundError:
        print(
            f"[ewf_tools] ERROR: executable not found: {exe_path}\n"
            f"Make sure the ewf/ directory contains {exe_name} or that it is "
            "installed on your PATH.",
            file=sys.stderr,
        )
        return 1
    finally:
        if stdin_file is not None:
            stdin_file.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wrapper for bundled EWF tools.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "subcommand",
        choices=list(TOOL_MAP.keys()),
        help="EWF tool to invoke",
    )
    # Capture everything after the subcommand and pass it through unchanged.
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the underlying executable",
    )

    parsed = parser.parse_args()
    sys.exit(run_tool(parsed.subcommand, parsed.args))


if __name__ == "__main__":
    main()
