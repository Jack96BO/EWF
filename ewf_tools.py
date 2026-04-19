#!/usr/bin/env python3
"""
ewf_tools.py - Strumento per la gestione di immagini forensi E01 (Expert Witness Format)

Permette di:
  - Leggere e visualizzare i metadati di file E01 tramite ewfinfo
  - Convertire file E01 in formato RAW tramite ewfexport
  - Convertire file RAW in formato E01 tramite ewfacquire

Utilizzo:
  python ewf_tools.py info <file.E01> [file.E02 ...]
  python ewf_tools.py to-raw <file.E01> [file.E02 ...] -o <destinazione>
  python ewf_tools.py to-e01 <file.raw> -o <destinazione> [-s <dimensione_segmento>]
"""

import subprocess
import sys
import os
import argparse

# Dimensione predefinita di ogni segmento E01: 5 GB
DEFAULT_SEGMENT_SIZE_BYTES = 5_000_000_000


def get_ewf_tool(tool_name: str) -> str:
    """
    Restituisce il percorso dello strumento EWF da usare.
    Cerca prima nella cartella 'ewf' relativa allo script, poi nel PATH di sistema.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(script_dir, "ewf", tool_name)
    if os.path.isfile(local_path):
        return local_path
    return tool_name


def ewf_info(image_files: list) -> int:
    """
    Esegue ewfinfo sui file immagine specificati e mostra i metadati.
    Restituisce il codice di uscita del processo.
    """
    tool = get_ewf_tool("ewfinfo.exe")
    cmd = [tool] + image_files
    print(f"[*] Esecuzione: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def ewf_to_raw(image_files: list, output_path: str) -> int:
    """
    Esegue ewfexport per convertire file E01 in formato RAW.
    Restituisce il codice di uscita del processo.
    """
    tool = get_ewf_tool("ewfexport.exe")
    cmd = [tool, "-t", output_path] + image_files
    print(f"[*] Esecuzione: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def ewf_to_e01(raw_file: str, output_path: str, segment_size: int = DEFAULT_SEGMENT_SIZE_BYTES) -> int:
    """
    Esegue ewfacquire per convertire un file RAW in formato E01.
    Restituisce il codice di uscita del processo.
    """
    tool = get_ewf_tool("ewfacquire.exe")
    cmd = [
        tool,
        "-f", "ewf",
        "-S", str(segment_size),
        "-t", output_path,
        raw_file,
    ]
    print(f"[*] Esecuzione: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Strumento per la gestione di immagini forensi E01 (Expert Witness Format)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  Visualizza i metadati di un file E01:
    python ewf_tools.py info immagine.E01
    python ewf_tools.py info immagine.E01 immagine.E02 immagine.E03

  Converti da E01 a RAW:
    python ewf_tools.py to-raw immagine.E01 -o output_raw
    python ewf_tools.py to-raw immagine.E01 immagine.E02 -o output_raw

  Converti da RAW a E01:
    python ewf_tools.py to-e01 immagine.raw -o immagine_e01
    python ewf_tools.py to-e01 immagine.001 -o immagine_e01 --segment-size 2000000000
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando da eseguire")

    # Sottocomando 'info': legge e mostra i metadati di un file E01
    info_parser = subparsers.add_parser(
        "info", help="Legge e visualizza i metadati di un file E01"
    )
    info_parser.add_argument(
        "image_files",
        nargs="+",
        metavar="FILE",
        help="Uno o più segmenti del file immagine E01 (es. immagine.E01 immagine.E02)",
    )

    # Sottocomando 'to-raw': converte da E01 a RAW
    to_raw_parser = subparsers.add_parser(
        "to-raw", help="Converte un file E01 in formato RAW"
    )
    to_raw_parser.add_argument(
        "image_files",
        nargs="+",
        metavar="FILE",
        help="Uno o più segmenti del file immagine E01 (es. immagine.E01 immagine.E02)",
    )
    to_raw_parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT",
        help="Percorso di destinazione per il file RAW (senza estensione)",
    )

    # Sottocomando 'to-e01': converte da RAW a E01
    to_e01_parser = subparsers.add_parser(
        "to-e01", help="Converte un file RAW in formato E01"
    )
    to_e01_parser.add_argument(
        "raw_file",
        metavar="FILE",
        help="File immagine RAW da convertire (es. immagine.raw o immagine.001)",
    )
    to_e01_parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT",
        help="Percorso di destinazione per il file E01 (senza estensione)",
    )
    to_e01_parser.add_argument(
        "-s",
        "--segment-size",
        type=int,
        default=DEFAULT_SEGMENT_SIZE_BYTES,
        metavar="BYTES",
        help="Dimensione massima di ogni segmento E01 in byte (default: 5000000000)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "info":
        sys.exit(ewf_info(args.image_files))
    elif args.command == "to-raw":
        sys.exit(ewf_to_raw(args.image_files, args.output))
    elif args.command == "to-e01":
        sys.exit(ewf_to_e01(args.raw_file, args.output, args.segment_size))


if __name__ == "__main__":
    main()
