#!/usr/bin/env python3
"""
read_e01.py - Script per la lettura e l'analisi di file E01 (Expert Witness Format)

Questo script permette di:
  - Visualizzare le informazioni/metadati di un file E01 tramite ewfinfo
  - Esportare il contenuto di un file E01 in formato raw tramite ewfexport

Utilizzo:
  python read_e01.py info <file.E01> [file.E02 ...]
  python read_e01.py export <file.E01> [file.E02 ...] -o <output>
"""

import subprocess
import sys
import os
import argparse


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
    Esegue ewfinfo sui file immagine specificati e mostra le informazioni.
    Restituisce il codice di uscita del processo.
    """
    tool = get_ewf_tool("ewfinfo.exe")
    cmd = [tool] + image_files
    print(f"[*] Esecuzione: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def ewf_export(image_files: list, output_path: str) -> int:
    """
    Esegue ewfexport per esportare il contenuto del file E01 nel percorso specificato.
    Restituisce il codice di uscita del processo.
    """
    tool = get_ewf_tool("ewfexport.exe")
    cmd = [tool, "-t", output_path] + image_files
    print(f"[*] Esecuzione: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Strumento per leggere e analizzare file E01 (Expert Witness Format)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  Visualizza informazioni su un file E01:
    python read_e01.py info immagine.E01
    python read_e01.py info immagine.E01 immagine.E02 immagine.E03

  Esporta il contenuto di un file E01 in formato raw:
    python read_e01.py export immagine.E01 -o output_raw
    python read_e01.py export immagine.E01 immagine.E02 -o output_raw
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Comando da eseguire")

    # Sottocomando 'info'
    info_parser = subparsers.add_parser(
        "info", help="Visualizza metadati e informazioni di un file E01"
    )
    info_parser.add_argument(
        "image_files",
        nargs="+",
        metavar="FILE",
        help="Uno o più segmenti del file immagine E01 (es. immagine.E01 immagine.E02)",
    )

    # Sottocomando 'export'
    export_parser = subparsers.add_parser(
        "export", help="Esporta il contenuto di un file E01 in formato raw"
    )
    export_parser.add_argument(
        "image_files",
        nargs="+",
        metavar="FILE",
        help="Uno o più segmenti del file immagine E01 (es. immagine.E01 immagine.E02)",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="OUTPUT",
        help="Percorso di destinazione per il file esportato (senza estensione)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "info":
        sys.exit(ewf_info(args.image_files))
    elif args.command == "export":
        sys.exit(ewf_export(args.image_files, args.output))


if __name__ == "__main__":
    main()
