#!/usr/bin/env python3
"""
Flask REST API server wrapping the EWF command-line tools.

Executables are resolved from the bundled ``ewf/`` directory that lives next
to this file, with an automatic fallback to whatever is on the system PATH.

Endpoints
---------
GET  /info               – ewfinfo   : show metadata for one or more E01 files
POST /acquire            – ewfacquire: acquire a physical device to EWF format
POST /acquire-stream     – ewfacquirestream: acquire a byte stream to EWF
POST /export             – ewfexport : convert EWF segment(s) to another format
POST /verify             – ewfverify : verify integrity of EWF segment(s)
POST /recover            – ewfrecover: recover data from damaged EWF segment(s)
POST /mount              – ewfmount  : mount EWF segment(s) as a virtual image
POST /debug              – ewfdebug  : print low-level debug information
"""

import logging
import os
import subprocess
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SEGMENT_SIZE = 2_147_483_648  # 2 GiB

# Whitelists for values that are passed as command-line flags
_VALID_FORMATS = {"ewf", "ex01", "lef", "raw", "encase1", "encase2", "encase3",
                  "encase4", "encase5", "encase6", "encase7", "smart", "ftk"}
_VALID_COMPRESSIONS = {"none", "empty-block", "deflate", "bzip2"}

# ---------------------------------------------------------------------------
# Helper: locate a bundled EWF executable
# ---------------------------------------------------------------------------

_EWF_DIR = Path(__file__).parent / "ewf"


def _tool(name: str) -> str:
    """Return the absolute path to *name* inside the bundled ewf/ directory.

    Falls back to just the bare executable name (PATH lookup) when the
    bundled copy does not exist – useful on Linux/macOS development machines.
    """
    candidate = _EWF_DIR / name
    if candidate.exists():
        return str(candidate)
    # Try without .exe extension on non-Windows hosts
    if name.endswith(".exe"):
        candidate_no_ext = _EWF_DIR / name[:-4]
        if candidate_no_ext.exists():
            return str(candidate_no_ext)
    return name


def _validate_value(value: str, whitelist: set) -> str | None:
    """Return *value* if it is in *whitelist*, otherwise None."""
    return value if value in whitelist else None


def _validate_format(value: str) -> str | None:
    """Return the format string if valid, or None."""
    return _validate_value(value, _VALID_FORMATS)


def _validate_compression(value: str) -> str | None:
    """Return the compression string if valid, or None."""
    return _validate_value(value, _VALID_COMPRESSIONS)


def _parse_int(value, default: int) -> tuple[int | None, str | None]:
    """Safely parse *value* as an integer.

    Returns ``(int_value, None)`` on success, or ``(None, error_message)``
    when the conversion fails.
    """
    if value is None:
        return default, None
    try:
        return int(value), None
    except (TypeError, ValueError):
        return None, f"Expected an integer, got: {value!r}"


def _run(cmd: list, timeout: int = 120) -> dict:
    """Execute *cmd* and return a JSON-serialisable result dict.

    The command is always called without a shell (shell=False by default),
    so arguments are passed directly to the executable and shell metacharacters
    in argument values are never interpreted by a shell.
    """
    try:
        result = subprocess.run(  # noqa: S603 – shell=False, args are a list
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (FileNotFoundError, PermissionError):
        logger.exception("Failed to execute: %s", cmd[0])
        return {"error": "Tool executable not found or not executable on this system"}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout} seconds"}


# ---------------------------------------------------------------------------
# /info  –  ewfinfo
# ---------------------------------------------------------------------------


@app.route("/info", methods=["GET", "POST"])
def info():
    """Return metadata for one or more EWF segment files.

    Query-string or JSON body
    -------------------------
    files : list[str] | str  – path(s) to the E01/EWx segment file(s)
    verbose : bool           – pass -v flag (default false)
    """
    data = request.get_json(silent=True) or {}
    files = data.get("files") or request.args.getlist("files")
    if isinstance(files, str):
        files = [files]
    if not files:
        return jsonify({"error": "At least one file path is required in 'files'"}), 400

    raw_verbose = data.get("verbose", request.args.get("verbose", False))
    if isinstance(raw_verbose, str):
        verbose = raw_verbose.lower() in ("1", "true", "yes")
    else:
        verbose = bool(raw_verbose)

    cmd = [_tool("ewfinfo.exe")]
    if verbose:
        cmd.append("-v")
    cmd.extend(files)

    return jsonify(_run(cmd))


# ---------------------------------------------------------------------------
# /acquire  –  ewfacquire
# ---------------------------------------------------------------------------


@app.route("/acquire", methods=["POST"])
def acquire():
    """Acquire a physical device/image to EWF format.

    JSON body fields
    ----------------
    source        : str   – source device or image path (required)
    target        : str   – target base name (required, passed as -t)
    format        : str   – EWF format, e.g. "ewf" / "ex01" (default "ewf")
    segment_size  : int   – max segment size in bytes (default 2 GiB)
    compression   : str   – compression type: "none"/"empty-block"/"deflate"
    case_number   : str   – case number metadata (-C)
    description   : str   – description metadata (-d)
    evidence_number: str  – evidence number metadata (-e)
    examiner_name : str   – examiner name metadata (-E)
    notes         : str   – notes metadata (-N)
    bytes_per_sector: int – bytes per sector (-b)
    """
    data = request.get_json(silent=True) or {}
    source = data.get("source")
    target = data.get("target")
    if not source or not target:
        return jsonify({"error": "'source' and 'target' are required"}), 400

    fmt = _validate_format(data.get("format", "ewf"))
    if fmt is None:
        return jsonify({"error": f"Invalid 'format'. Allowed: {sorted(_VALID_FORMATS)}"}), 400

    compression = data.get("compression")
    if compression and _validate_compression(compression) is None:
        return jsonify({"error": f"Invalid 'compression'. Allowed: {sorted(_VALID_COMPRESSIONS)}"}), 400

    segment_size, err = _parse_int(data.get("segment_size"), DEFAULT_SEGMENT_SIZE)
    if err:
        return jsonify({"error": f"'segment_size': {err}"}), 400

    cmd = [_tool("ewfacquire.exe")]
    cmd += ["-f", fmt]
    cmd += ["-S", str(segment_size)]
    cmd += ["-t", target]

    if compression:
        cmd += ["-c", compression]
    if data.get("case_number"):
        cmd += ["-C", str(data["case_number"])]
    if data.get("description"):
        cmd += ["-d", str(data["description"])]
    if data.get("evidence_number"):
        cmd += ["-e", str(data["evidence_number"])]
    if data.get("examiner_name"):
        cmd += ["-E", str(data["examiner_name"])]
    if data.get("notes"):
        cmd += ["-N", str(data["notes"])]
    if data.get("bytes_per_sector") is not None:
        bps, err = _parse_int(data["bytes_per_sector"], None)
        if err:
            return jsonify({"error": f"'bytes_per_sector': {err}"}), 400
        cmd += ["-b", str(bps)]

    cmd.append(source)
    return jsonify(_run(cmd, timeout=3600))


# ---------------------------------------------------------------------------
# /acquire-stream  –  ewfacquirestream
# ---------------------------------------------------------------------------


@app.route("/acquire-stream", methods=["POST"])
def acquire_stream():
    """Acquire a byte stream (stdin) into an EWF image.

    JSON body fields
    ----------------
    target        : str   – target base name (required, passed as -t)
    format        : str   – EWF format (default "ewf")
    segment_size  : int   – max segment size in bytes (default 2 GiB)
    compression   : str   – compression type
    case_number   : str
    description   : str
    evidence_number: str
    examiner_name : str
    notes         : str
    bytes_per_sector: int
    """
    data = request.get_json(silent=True) or {}
    target = data.get("target")
    if not target:
        return jsonify({"error": "'target' is required"}), 400

    fmt = _validate_format(data.get("format", "ewf"))
    if fmt is None:
        return jsonify({"error": f"Invalid 'format'. Allowed: {sorted(_VALID_FORMATS)}"}), 400

    compression = data.get("compression")
    if compression and _validate_compression(compression) is None:
        return jsonify({"error": f"Invalid 'compression'. Allowed: {sorted(_VALID_COMPRESSIONS)}"}), 400

    segment_size, err = _parse_int(data.get("segment_size"), DEFAULT_SEGMENT_SIZE)
    if err:
        return jsonify({"error": f"'segment_size': {err}"}), 400

    cmd = [_tool("ewfacquirestream.exe")]
    cmd += ["-f", fmt]
    cmd += ["-S", str(segment_size)]
    cmd += ["-t", target]

    if compression:
        cmd += ["-c", compression]
    if data.get("case_number"):
        cmd += ["-C", str(data["case_number"])]
    if data.get("description"):
        cmd += ["-d", str(data["description"])]
    if data.get("evidence_number"):
        cmd += ["-e", str(data["evidence_number"])]
    if data.get("examiner_name"):
        cmd += ["-E", str(data["examiner_name"])]
    if data.get("notes"):
        cmd += ["-N", str(data["notes"])]
    if data.get("bytes_per_sector") is not None:
        bps, err = _parse_int(data["bytes_per_sector"], None)
        if err:
            return jsonify({"error": f"'bytes_per_sector': {err}"}), 400
        cmd += ["-b", str(bps)]

    return jsonify(_run(cmd, timeout=3600))


# ---------------------------------------------------------------------------
# /export  –  ewfexport
# ---------------------------------------------------------------------------


@app.route("/export", methods=["POST"])
def export():
    """Convert EWF segment(s) to raw or another EWF format.

    JSON body fields
    ----------------
    files         : list[str] | str – input segment file(s) (required)
    target        : str             – output base name (-t)
    format        : str             – output format: "raw"/"ewf"/"ex01" etc.
    segment_size  : int             – max output segment size in bytes
    compression   : str             – compression type for output
    """
    data = request.get_json(silent=True) or {}
    files = data.get("files")
    if isinstance(files, str):
        files = [files]
    if not files:
        return jsonify({"error": "'files' (list of input paths) is required"}), 400

    fmt = data.get("format")
    if fmt and _validate_format(fmt) is None:
        return jsonify({"error": f"Invalid 'format'. Allowed: {sorted(_VALID_FORMATS)}"}), 400

    compression = data.get("compression")
    if compression and _validate_compression(compression) is None:
        return jsonify({"error": f"Invalid 'compression'. Allowed: {sorted(_VALID_COMPRESSIONS)}"}), 400

    cmd = [_tool("ewfexport.exe")]
    if fmt:
        cmd += ["-f", fmt]
    if data.get("target"):
        cmd += ["-t", data["target"]]
    if data.get("segment_size") is not None:
        seg, err = _parse_int(data["segment_size"], None)
        if err:
            return jsonify({"error": f"'segment_size': {err}"}), 400
        cmd += ["-S", str(seg)]
    if compression:
        cmd += ["-c", compression]

    cmd.extend(files)
    return jsonify(_run(cmd, timeout=3600))


# ---------------------------------------------------------------------------
# /verify  –  ewfverify
# ---------------------------------------------------------------------------


@app.route("/verify", methods=["POST"])
def verify():
    """Verify the integrity (checksums) of EWF segment(s).

    JSON body fields
    ----------------
    files   : list[str] | str – path(s) to the segment file(s) (required)
    verbose : bool            – pass -v flag
    """
    data = request.get_json(silent=True) or {}
    files = data.get("files")
    if isinstance(files, str):
        files = [files]
    if not files:
        return jsonify({"error": "'files' is required"}), 400

    verbose = bool(data.get("verbose", False))
    cmd = [_tool("ewfverify.exe")]
    if verbose:
        cmd.append("-v")
    cmd.extend(files)
    return jsonify(_run(cmd, timeout=3600))


# ---------------------------------------------------------------------------
# /recover  –  ewfrecover
# ---------------------------------------------------------------------------


@app.route("/recover", methods=["POST"])
def recover():
    """Recover data from damaged EWF segment(s).

    JSON body fields
    ----------------
    files   : list[str] | str – input segment file(s) (required)
    target  : str             – output base name (-t)
    format  : str             – output format
    verbose : bool
    """
    data = request.get_json(silent=True) or {}
    files = data.get("files")
    if isinstance(files, str):
        files = [files]
    if not files:
        return jsonify({"error": "'files' is required"}), 400

    fmt = data.get("format")
    if fmt and _validate_format(fmt) is None:
        return jsonify({"error": f"Invalid 'format'. Allowed: {sorted(_VALID_FORMATS)}"}), 400

    cmd = [_tool("ewfrecover.exe")]
    if fmt:
        cmd += ["-f", fmt]
    if data.get("target"):
        cmd += ["-t", data["target"]]
    if data.get("verbose"):
        cmd.append("-v")

    cmd.extend(files)
    return jsonify(_run(cmd, timeout=3600))


# ---------------------------------------------------------------------------
# /mount  –  ewfmount
# ---------------------------------------------------------------------------


@app.route("/mount", methods=["POST"])
def mount():
    """Mount EWF segment(s) as a virtual image via FUSE.

    JSON body fields
    ----------------
    files       : list[str] | str – input segment file(s) (required)
    mount_point : str             – directory to mount the image on (required)
    """
    data = request.get_json(silent=True) or {}
    files = data.get("files")
    if isinstance(files, str):
        files = [files]
    mount_point = data.get("mount_point")
    if not files or not mount_point:
        return jsonify({"error": "'files' and 'mount_point' are required"}), 400

    cmd = [_tool("ewfmount.exe")]
    cmd.extend(files)
    cmd.append(mount_point)
    return jsonify(_run(cmd, timeout=60))


# ---------------------------------------------------------------------------
# /debug  –  ewfdebug
# ---------------------------------------------------------------------------


@app.route("/debug", methods=["POST"])
def debug():
    """Print low-level debug information for EWF segment(s).

    JSON body fields
    ----------------
    files   : list[str] | str – path(s) to the segment file(s) (required)
    """
    data = request.get_json(silent=True) or {}
    files = data.get("files")
    if isinstance(files, str):
        files = [files]
    if not files:
        return jsonify({"error": "'files' is required"}), 400

    cmd = [_tool("ewfdebug.exe")]
    cmd.extend(files)
    return jsonify(_run(cmd))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # NOTE: The Flask development server is for local testing only.
    # For production deployments use a proper WSGI server such as Gunicorn:
    #   gunicorn -w 4 ewf_tools:app
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=False)
