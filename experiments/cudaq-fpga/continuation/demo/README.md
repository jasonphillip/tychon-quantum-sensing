# Three-minute technical demonstration

Prepared October 17, 2026. This demonstration reads saved evidence and verifies its hashes.
It does not run a new GPU experiment or communicate with the FPGA.

## Run the evidence display

From any Python 3.11+ environment, supply the extracted workspace's absolute path:

```sh
python3 /ABSOLUTE/PACKAGE/PATH/demo/show_evidence.py --root /ABSOLUTE/PACKAGE/PATH --manifest demo/evidence_manifest.json
```

The program stops before displaying facts if an evidence file is missing or altered.
Its manifest binds each displayed fact to saved evidence files.
This checks file integrity and references. It does not independently adjudicate scientific claims.

A portable equivalent is:

```sh
python3 ./demo/show_evidence.py --root . --manifest demo/evidence_manifest.json
```

It verifies 27 saved files and displays nine scoped facts.


The main package README explains the successful results, failed gates, and limits.
