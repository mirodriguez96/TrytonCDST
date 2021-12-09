from trytond.wizard import Wizard, StateTransition
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.pool import Pool
from it_supplier_noova import ElectronicPayrollCdst


class PayrollElectronicCdst(Wizard):
    'Payroll Electronic Cdst'
    __name__ = 'staff.payroll_electronic.it_supplier'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        PayrollElectronic = Pool().get('staff.payroll.electronic')
        ids = Transaction().context['active_ids']

        for payroll in PayrollElectronic.browse(ids):
            if payroll.state == 'processed' and payroll.electronic_state != 'authorized':
                if payroll.payroll_type is None:
                    continue
                if payroll.validate_for_send():
                    pool = Pool()
                    Configuration = pool.get('staff.configuration')
                    configuration = Configuration(1)
                    _ = ElectronicPayrollCdst(payroll, configuration)
                else:
                    payroll.get_message('Nomina no valida para enviar')
            else:
                payroll.get_message('Nomina no valida para enviar (revisar estado de la nómina).')
        return 'end'