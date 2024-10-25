#!/bin/sh

modules="
trytoncdst_access
trytoncdst_conector
"

echo "[INFO] Uninstalling trytoncdst modules... "
for i in ${modules}
    do
        pip uninstall -y $i
    done
echo "[INFO] Done. "


echo "[INFO] Installing trytoncdst modules... "
for i in ${modules}
    do
        cd $i
        pip install .
        cd ..
    done
echo "[INFO] Done. "