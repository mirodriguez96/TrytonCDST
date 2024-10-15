from datetime import datetime, time
from decimal import Decimal

from sql import Table

from trytond.exceptions import UserWarning
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.wizard import StateTransition, Wizard

from . import fixes

STATE_LOG = [
    ('pending', 'Pending'),
    ('in_progress', 'In progress'),
    ('done', 'Done'),
]


class ConectorLog(ModelSQL, ModelView):
    'Conector Log'
    __name__ = 'conector.log'

    actualizacion = fields.Many2One('conector.actualizacion',
                                    'log',
                                    'Actualizacion',
                                    required=True)
    event_time = fields.DateTime('Event time', required=True)
    id_tecno = fields.Char('Id TecnoCarnes',
                           help='For documents sw-tipo-numero',
                           required=True)
    message = fields.Char('Message', required=True)
    state = fields.Selection(STATE_LOG, 'State', required=True)

    @staticmethod
    def default_state():
        return 'pending'

    @classmethod
    def delete_data_log(cls, id_logs=None):
        """Function to delete data log"""

        pool = Pool()
        ConectorLog = pool.get('conector.log')
        date_today = datetime.combine(datetime.now().date(), time.min)

        if id_logs:
            to_delete = ConectorLog.search(
                [('actualizacion.id', 'in', id_logs)])
        else:
            to_delete = ConectorLog.search([('event_time', '<', date_today)])
        ConectorLog.delete(to_delete)


class DeleteImportRecords(Wizard):
    'Delete Import Records'
    __name__ = 'conector.actualizacion.delete_import_records'
    start_state = 'do_submit'
    do_submit = StateTransition()

    def transition_do_submit(self):
        """Function to delete data log selected

        Raises:
            UserWarning: to announce to the user
                        that records will be deleted

        Returns:
            String: return end to finally wizard
        """
        pool = Pool()
        Warning = pool.get('res.user.warning')
        ConectorLog = pool.get('conector.log')
        ids = Transaction().context['active_ids']

        # Se agrega un nombre unico a la advertencia
        warning_name = 'warning_delete_import_records'
        if Warning.check(warning_name):
            raise UserWarning(
                warning_name,
                "Los registros de la actualización serán eliminados.")
        if ids:
            ConectorLog.delete_data_log(ids)
        return 'end'

    def end(self):
        return 'reload'
