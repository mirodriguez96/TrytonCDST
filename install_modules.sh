#!/bin/sh

modules="
account_bank_statement_cdst
account_cdst
account_invoice_cdst
company_cdst
conector_cdst
configuration_cdst
contract_cdst
electronic_payroll_cdst
metabase_cdst
party_cdst
permissions_cdst
product_cdst
production_cdst
purchase_cdst
report_cdst
sale_cdst
staff_liquidation_cdst
staff_loan_cdst
staff_payroll_cdst
stock_cdst
tax_cdst
voucher_cdst
wiz_cdst
"



echo "[INFO] Uninstalling trytoncdst modules... "
pip uninstall -y trytoncdst_access trytoncdst_conector
for i in ${modules}
    do
        pip uninstall -y trytond-$i
    done
echo "[INFO] Done. "


echo "[INFO] Installing trytoncdst modules... "
pip install trytoncdst_access trytoncdst_conector
for i in ${modules}
    do
        cd $i
        pip install .
        cd ..
    done
echo "[INFO] Done. "