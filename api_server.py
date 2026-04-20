#!/usr/bin/env python3
"""
api_server.py - Flask REST API for E01/EWF orchestration.

Exposes HTTP endpoints for the operations implemented by ewf_tools.py and
read_e01.py so acquisition, conversion, verification, mounting and browsing
can be orchestrated over localhost:9901.
"""

import base64
import json
import os
import subprocess
import sys

from flask import Flask, jsonify, request


HOST = os.getenv("EWF_API_HOST", "127.0.0.1")
PORT = int(os.getenv("EWF_API_PORT", "9901"))
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_BIN = sys.executable
EWF_SCRIPT = os.path.join(ROOT_DIR, "ewf_tools.py")
READ_SCRIPT = os.path.join(ROOT_DIR, "read_e01.py")

app = Flask(__name__)


def _payload() -> dict:
    return request.get_json(silent=True) or {}


def _error(message: str, status_code: int = 400):
    return jsonify({"success": False, "error": message}), status_code


def _require(payload: dict, key: str):
    value = payload.get(key)
    if value in (None, "", []):
        raise ValueError(f"Missing required field: {key}")
    return value


def _add_flag(args: list[str], payload: dict, field: str, flag: str):
    value = payload.get(field)
    if value not in (None, ""):
        args.extend([flag, str(value)])


def _add_bool_flag(args: list[str], payload: dict, field: str, flag: str):
    if payload.get(field):
        args.append(flag)


def _add_multi_flag(args: list[str], payload: dict, field: str, flag: str):
    values = payload.get(field) or []
    for value in values:
        args.extend([flag, str(value)])


def _add_images(args: list[str], images):
    if isinstance(images, str):
        args.append(images)
        return
    for image in images:
        args.append(str(image))


def _run_script(script_path: str, command_args: list[str], stdin_bytes: bytes | None = None):
    process = subprocess.run(
        [PYTHON_BIN, script_path] + command_args,
        input=stdin_bytes,
        capture_output=True,
        cwd=ROOT_DIR,
    )
    return process


def _text_response(process: subprocess.CompletedProcess, status_code: int = 200):
    return (
        jsonify(
            {
                "success": process.returncode == 0,
                "exit_code": process.returncode,
                "stdout": process.stdout.decode("utf-8", errors="replace"),
                "stderr": process.stderr.decode("utf-8", errors="replace"),
            }
        ),
        status_code,
    )


def _binary_response(process: subprocess.CompletedProcess, status_code: int = 200):
    return (
        jsonify(
            {
                "success": process.returncode == 0,
                "exit_code": process.returncode,
                "stdout_base64": base64.b64encode(process.stdout).decode("ascii"),
                "stdout_size": len(process.stdout),
                "stderr": process.stderr.decode("utf-8", errors="replace"),
            }
        ),
        status_code,
    )


@app.get("/health")
def health():
    return jsonify({"success": True, "service": "ewf-api", "host": HOST, "port": PORT})


@app.get("/")
def index():
    return jsonify(
        {
            "success": True,
            "service": "ewf-api",
            "endpoints": [
                "/health",
                "/ewf/info",
                "/ewf/acquire",
                "/ewf/acquire-stream",
                "/ewf/export",
                "/ewf/verify",
                "/ewf/recover",
                "/ewf/mount",
                "/ewf/unmount",
                "/ewf/mounts",
                "/ewf/debug",
                "/read/info",
                "/read/ls",
                "/read/tree",
                "/read/cat",
                "/read/extract",
            ],
        }
    )


@app.post("/ewf/info")
def ewf_info():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["info"]
    _add_flag(args, payload, "date_format", "-d")
    _add_flag(args, payload, "header_format", "-f")
    _add_bool_flag(args, payload, "verbose", "-v")
    _add_images(args, images)
    return _text_response(_run_script(EWF_SCRIPT, args))


@app.post("/ewf/acquire")
def ewf_acquire():
    payload = _payload()
    try:
        source = _require(payload, "source")
    except ValueError as exc:
        return _error(str(exc))

    args = ["acquire"]
    _add_flag(args, payload, "format", "-f")
    _add_flag(args, payload, "target", "-t")
    _add_flag(args, payload, "segment_size", "-S")
    _add_flag(args, payload, "compression", "-c")
    _add_flag(args, payload, "bytes_per_sector", "-b")
    _add_flag(args, payload, "sectors_per_chunk", "-s")
    _add_flag(args, payload, "case_number", "-C")
    _add_flag(args, payload, "description", "-D")
    _add_flag(args, payload, "evidence_number", "-e")
    _add_flag(args, payload, "examiner", "-E")
    _add_flag(args, payload, "notes", "-N")
    _add_flag(args, payload, "media_type", "-m")
    _add_flag(args, payload, "media_flags", "-M")
    _add_multi_flag(args, payload, "hash", "-d")
    _add_flag(args, payload, "read_error_retry", "-r")
    _add_bool_flag(args, payload, "resume", "-R")
    _add_bool_flag(args, payload, "no_prompt", "-u")
    _add_bool_flag(args, payload, "verbose", "-v")
    args.append(str(source))
    return _text_response(_run_script(EWF_SCRIPT, args))


@app.post("/ewf/acquire-stream")
def ewf_acquire_stream():
    payload = _payload()
    args = ["acquire-stream"]
    _add_flag(args, payload, "input", "-i")
    _add_flag(args, payload, "format", "-f")
    _add_flag(args, payload, "target", "-t")
    _add_flag(args, payload, "segment_size", "-S")
    _add_flag(args, payload, "compression", "-c")
    _add_flag(args, payload, "bytes_per_sector", "-b")
    _add_flag(args, payload, "sectors_per_chunk", "-s")
    _add_flag(args, payload, "case_number", "-C")
    _add_flag(args, payload, "description", "-D")
    _add_flag(args, payload, "evidence_number", "-e")
    _add_flag(args, payload, "examiner", "-E")
    _add_flag(args, payload, "notes", "-N")
    _add_flag(args, payload, "media_type", "-m")
    _add_multi_flag(args, payload, "hash", "-d")
    _add_bool_flag(args, payload, "no_prompt", "-u")
    _add_bool_flag(args, payload, "verbose", "-v")

    stdin_bytes = None
    if payload.get("data_base64"):
        try:
            stdin_bytes = base64.b64decode(payload["data_base64"], validate=True)
        except Exception:
            return _error("Invalid base64 payload in data_base64")
    elif not payload.get("input"):
        return _error("Provide either input or data_base64")

    return _text_response(_run_script(EWF_SCRIPT, args, stdin_bytes=stdin_bytes))


@app.post("/ewf/export")
def ewf_export():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["export"]
    _add_flag(args, payload, "format", "-f")
    _add_flag(args, payload, "target", "-t")
    _add_flag(args, payload, "segment_size", "-S")
    _add_flag(args, payload, "compression", "-c")
    _add_flag(args, payload, "offset", "-o")
    _add_flag(args, payload, "size", "-s")
    _add_multi_flag(args, payload, "hash", "-d")
    _add_bool_flag(args, payload, "no_prompt", "-u")
    _add_bool_flag(args, payload, "verbose", "-v")
    _add_images(args, images)
    return _text_response(_run_script(EWF_SCRIPT, args))


@app.post("/ewf/verify")
def ewf_verify():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["verify"]
    _add_multi_flag(args, payload, "hash", "-d")
    _add_bool_flag(args, payload, "verbose", "-v")
    _add_images(args, images)
    return _text_response(_run_script(EWF_SCRIPT, args))


@app.post("/ewf/recover")
def ewf_recover():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["recover"]
    _add_flag(args, payload, "target", "-t")
    _add_bool_flag(args, payload, "verbose", "-v")
    _add_images(args, images)
    return _text_response(_run_script(EWF_SCRIPT, args))


@app.post("/ewf/mount")
def ewf_mount():
    payload = _payload()
    try:
        images = _require(payload, "images")
        mount_point = _require(payload, "mount_point")
    except ValueError as exc:
        return _error(str(exc))

    args = ["mount"]
    _add_bool_flag(args, payload, "verbose", "-v")
    _add_images(args, images)
    args.append(str(mount_point))
    return _text_response(_run_script(EWF_SCRIPT, args))


@app.post("/ewf/unmount")
def ewf_unmount():
    payload = _payload()
    try:
        mount_point = _require(payload, "mount_point")
    except ValueError as exc:
        return _error(str(exc))

    return _text_response(_run_script(EWF_SCRIPT, ["unmount", str(mount_point)]))


@app.get("/ewf/mounts")
def ewf_mounts():
    args = ["mounts"]
    include_stale = request.args.get("all", "false").lower() in {"1", "true", "yes"}
    if include_stale:
        args.append("--all")

    process = _run_script(EWF_SCRIPT, args)
    if process.returncode != 0:
        return _text_response(process, status_code=500)

    try:
        payload = json.loads(process.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return _text_response(process)

    payload["success"] = True
    payload["exit_code"] = 0
    return jsonify(payload)


@app.post("/ewf/debug")
def ewf_debug():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["debug"]
    _add_bool_flag(args, payload, "verbose", "-v")
    _add_images(args, images)
    return _text_response(_run_script(EWF_SCRIPT, args))


@app.post("/read/info")
def read_info():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["info"]
    _add_images(args, images)
    return _text_response(_run_script(READ_SCRIPT, args))


@app.post("/read/ls")
def read_ls():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["ls"]
    _add_images(args, images)
    args.append(str(payload.get("path") or "/"))
    return _text_response(_run_script(READ_SCRIPT, args))


@app.post("/read/tree")
def read_tree():
    payload = _payload()
    try:
        images = _require(payload, "images")
    except ValueError as exc:
        return _error(str(exc))

    args = ["tree"]
    _add_images(args, images)
    args.append(str(payload.get("path") or "/"))
    _add_flag(args, payload, "max_depth", "--max-depth")
    return _text_response(_run_script(READ_SCRIPT, args))


@app.post("/read/cat")
def read_cat():
    payload = _payload()
    try:
        images = _require(payload, "images")
        internal_path = _require(payload, "internal_path")
    except ValueError as exc:
        return _error(str(exc))

    args = ["cat"]
    _add_images(args, images)
    args.append(str(internal_path))
    return _binary_response(_run_script(READ_SCRIPT, args))


@app.post("/read/extract")
def read_extract():
    payload = _payload()
    try:
        images = _require(payload, "images")
        internal_path = _require(payload, "internal_path")
    except ValueError as exc:
        return _error(str(exc))

    args = ["extract"]
    _add_images(args, images)
    args.append(str(internal_path))
    _add_flag(args, payload, "output", "-o")
    return _text_response(_run_script(READ_SCRIPT, args))


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)