#!/usr/bin/env python3
"""Quick Windows test harness for rawCopyXsector.dll.

Usage examples (run on Windows):
  py rawcopyxsector_windows_test.py list --dll .\\Release\\rawCopyXsector.dll
  py rawcopyxsector_windows_test.py copy --source "\\\\.\\PhysicalDrive1" --output C:\\temp\\disk1.raw --overwrite
"""

from __future__ import annotations

import argparse
import ctypes
import os
import platform
import sys
from ctypes import c_bool, c_char_p
from pathlib import Path


DEFAULT_DLL = Path("Release") / "rawCopyXsector.dll"


class RawCopyLoadError(RuntimeError):
    """Raised when the DLL cannot be loaded or does not expose expected APIs."""


def _ensure_windows() -> None:
    if platform.system().lower() != "windows":
        raise RuntimeError("Questo script va eseguito su Windows (PowerShell o CMD).")


def _resolve_dll_path(dll_path: str | None) -> Path:
    if dll_path:
        return Path(dll_path).expanduser().resolve()
    return DEFAULT_DLL.resolve()


def _normalize_source_path(source: str) -> str:
    # Accept common typo "\.\PhysicalDriveN" and normalize to "\\.\PhysicalDriveN".
    if source.startswith("\\\\.\\PhysicalDrive"):
        return source
    if source.startswith("\\.\\PhysicalDrive"):
        return "\\" + source
    return source


def load_library(dll_path: str | None):
    _ensure_windows()
    path = _resolve_dll_path(dll_path)

    if not path.exists():
        raise RawCopyLoadError(f"DLL non trovata: {path}")

    try:
        lib = ctypes.WinDLL(str(path))
    except OSError as exc:
        raise RawCopyLoadError(f"Impossibile caricare la DLL: {path} ({exc})") from exc

    try:
        list_drives = lib.ListDrives
        raw_copy = lib.RawCopy
    except AttributeError as exc:
        raise RawCopyLoadError(
            "La DLL non espone i simboli attesi: ListDrives e RawCopy"
        ) from exc

    list_drives.argtypes = []
    list_drives.restype = c_bool

    raw_copy.argtypes = [c_char_p, c_char_p]
    raw_copy.restype = c_bool

    return lib


def cmd_list(args: argparse.Namespace) -> int:
    lib = load_library(args.dll)
    ok = bool(lib.ListDrives())
    print(f"ListDrives -> {ok}")
    return 0 if ok else 2


def cmd_copy(args: argparse.Namespace) -> int:
    lib = load_library(args.dll)

    source = _normalize_source_path(args.source)
    if source != args.source:
        print(f"Source normalizzato: {source}")

    source_b = source.encode("utf-8")
    output_b = args.output.encode("utf-8")

    print(f"Source: {source}")
    print(f"Output: {args.output}")
    if os.path.exists(args.output) and not args.overwrite:
        print("Il file di output esiste gia. Usa --overwrite per sovrascrivere.")
        return 3

    ok = bool(lib.RawCopy(source_b, output_b))
    print(f"RawCopy -> {ok}")

    if ok:
        out_path = Path(args.output)
        if out_path.exists():
            print(f"Output size: {out_path.stat().st_size} bytes")
        return 0

    print(
        "RawCopy ha restituito false. Controlla privilegi admin e usa il formato \\\\.\\PhysicalDriveN"
    )
    return 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test rapido per rawCopyXsector.dll (solo Windows)."
    )
    parser.add_argument(
        "--dll",
        default=None,
        help="Percorso della DLL (default: ./Release/rawCopyXsector.dll)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="Invoca ListDrives()")
    p_list.set_defaults(func=cmd_list)

    p_copy = sub.add_parser("copy", help="Invoca RawCopy(source, output)")
    p_copy.add_argument(
        "--source",
        required=True,
        help=r"Device sorgente, esempio: \\\\.\\PhysicalDrive1",
    )
    p_copy.add_argument(
        "--output",
        required=True,
        help="Path file output, esempio: C:\\temp\\disk1.raw",
    )
    p_copy.add_argument(
        "--overwrite",
        action="store_true",
        help="Permette di sovrascrivere il file output se esiste",
    )
    p_copy.set_defaults(func=cmd_copy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except RawCopyLoadError as exc:
        print(str(exc), file=sys.stderr)
        return 10
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 11
    except Exception as exc:
        print(f"Errore inatteso: {exc}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
