#!/bin/sh

modules="
trytoncdst_access
trytoncdst_conector
configuration_cdst
purchase_cdst
company_cdst
account_invoice_cdst
staff_loan_cdst
electronic_payroll_cdst
party_cdst
staff_liquidation_cdst
contract_cdst
staff_payroll_cdst
account_bank_statement_cdst
voucher_cdst
metabase_cdst
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