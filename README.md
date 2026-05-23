# EWF API e strumenti E01

Questo repository contiene tre componenti complementari:

- ewf_tools.py: generazione, conversione, verifica, recupero, debug e mount di immagini E01/EWF.
- read_e01.py: lettura del filesystem interno, listing, tree, cat ed estrazione file.
- api_server.py: orchestrazione HTTP di tutte le funzioni esposte dalle due CLI.

## Avvio API

Installazione minima:

```bash
python3 -m pip install -r requirements.txt
```

Uso dei tool libewf inclusi nel repository:

- la cartella [ewf](ewf) contiene i binari libewf bundled;
- nel progetto sono presenti binari Windows `.exe`, quindi su Windows vengono eseguiti direttamente;
- su Linux o macOS puoi usare i tool nativi installati nel sistema oppure Wine per eseguire i `.exe` inclusi.

Dipendenze utili lato sistema:

```bash
sudo apt-get install ewf-tools
```

Se vuoi usare i binari `.exe` inclusi dal repository anche su Linux:

```bash
sudo apt-get install wine
```

Per browsing completo del filesystem interno servono anche:

```bash
sudo apt-get install libewf-dev libtsk-dev python3-dev
python3 -m pip install pyewf pytsk3
```

Avvio server su localhost porta 9901:

```bash
python3 api_server.py
```

Health check:

```bash
curl http://127.0.0.1:9901/health
```

Menu API in italiano:

```bash
curl http://127.0.0.1:9901/menu
```

## Endpoint disponibili

GET:

- /health
- /
- /menu
- /ewf/mounts

POST:

- /ewf/info
- /ewf/acquire
- /ewf/acquire-stream
- /ewf/rawCopyXsector
- /ewf/rawCopyXsectorCpp
- /ewf/export
- /ewf/verify
- /ewf/recover
- /ewf/mount
- /ewf/unmount
- /ewf/debug
- /read/info
- /read/ls
- /read/tree
- /read/cat
- /read/extract

## Esempi payload

Informazioni immagine:

```bash
curl -X POST http://127.0.0.1:9901/ewf/info \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "verbose": true
  }'
```

Creazione E01 da device:

```bash
curl -X POST http://127.0.0.1:9901/ewf/acquire \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "/dev/sdb",
    "target": "/evidence/case001/disk",
    "format": "ewf",
    "compression": "fast",
    "case_number": "2026-001",
    "examiner": "Mario Rossi",
    "description": "Acquisizione disco",
    "no_prompt": true
  }'
```

Conversione raw in E01:

```bash
curl -X POST http://127.0.0.1:9901/ewf/acquire-stream \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "/images/disk.raw",
    "target": "/evidence/disk_converted",
    "compression": "best",
    "no_prompt": true
  }'
```

Copia raw settore-per-settore:

```bash
curl -X POST http://127.0.0.1:9901/ewf/rawCopyXsector \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "/images/disk.raw",
    "output": "/exports/slice.raw",
    "bytes_per_sector": 512,
    "start_sector": 2048,
    "sector_count": 4096,
    "force": true
  }'
```

Fallback C++ RawCopyXsector (solo Windows con DLL disponibile):

```bash
curl -X POST http://127.0.0.1:9901/ewf/rawCopyXsectorCpp \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "\\\\.\\PhysicalDrive1",
    "output": "C:/evidence/fallback.img",
    "dll_path": "C:/tools/rawCopyXsector.dll"
  }'
```

Esportazione E01 in raw:

```bash
curl -X POST http://127.0.0.1:9901/ewf/export \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "format": "raw",
    "target": "/exports/disk_raw",
    "no_prompt": true
  }'
```

Verifica integrita:

```bash
curl -X POST http://127.0.0.1:9901/ewf/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "hash": ["md5", "sha1"]
  }'
```

Mount E01:

```bash
curl -X POST http://127.0.0.1:9901/ewf/mount \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "mount_point": "/mnt/e01"
  }'
```

Lista mount gestiti:

```bash
curl http://127.0.0.1:9901/ewf/mounts
curl http://127.0.0.1:9901/ewf/mounts?all=true
```

Unmount E01:

```bash
curl -X POST http://127.0.0.1:9901/ewf/unmount \
  -H 'Content-Type: application/json' \
  -d '{
    "mount_point": "/mnt/e01"
  }'
```

Lista file interni:

```bash
curl -X POST http://127.0.0.1:9901/read/ls \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "path": "/Windows/System32"
  }'
```

Albero filesystem:

```bash
curl -X POST http://127.0.0.1:9901/read/tree \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "path": "/",
    "max_depth": 3
  }'
```

Lettura file interno come base64:

```bash
curl -X POST http://127.0.0.1:9901/read/cat \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "internal_path": "/Windows/System32/drivers/etc/hosts"
  }'
```

Estrazione file o directory:

```bash
curl -X POST http://127.0.0.1:9901/read/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "images": ["/cases/disk.E01"],
    "internal_path": "/Users/Test/Desktop",
    "output": "/tmp/extracted"
  }'
```

## Note operative

- L'API riusa le CLI esistenti, quindi stdout e stderr dei tool vengono restituiti in JSON.
- /read/cat restituisce stdout_base64 per evitare corruzione di contenuti binari.
- Il repository include binari libewf bundled, ma nel workspace corrente sono binari Windows `.exe`; su Linux servono Wine oppure i pacchetti nativi ewf-tools.
- Il mount richiede supporto FUSE e tool ewfmount disponibili o via pacchetto nativo o via bundle eseguibile.
- Per la gestione mount conviene usare i pacchetti nativi su Linux: in questo ambiente `umount` e' presente, mentre `wine` e tool libewf nativi non risultano installati.
- Il browsing di filesystem interno richiede pyewf e pytsk3.
- La UI del progetto `iso back-copia fisica` e' stata estesa per orchestrare tutte le funzioni EWF/Read e il fallback RawCopyXsector (API e C++).
- Nella UI sono disponibili: selettore DLL C++ (browse + auto-detect), fallback automatico in sequenza (API/C++) e preset dedicati per ogni endpoint EWF.
- L'endpoint `/ewf/rawCopyXsectorCpp` richiede Windows e una DLL valida (`RAWCOPYXSECTOR_DLL` o `dll_path` nel payload).