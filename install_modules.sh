#!/bin/sh

modules="
trytoncdst_access
trytoncdst_conector
"

echo "[INFO] Uninstalling trytoncdst modules... "
for i in ${modules}
    do
        pip uninstall $i
    done
echo "[INFO] Done. "


echo "[INFO] Installing trytoncdst modules... "
for i in ${modules}
    do
        cd $i
        pip install -e .
        cd ..
    done
echo "[INFO] Done. "