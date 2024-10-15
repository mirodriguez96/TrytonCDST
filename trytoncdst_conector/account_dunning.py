# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.exceptions import UserError
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.wizard import StateTransition, Wizard


class DunningForceDraft(Wizard):
    'Account Dunning Force Draft'
    __name__ = 'account.dunning.force_draft'
    start_state = 'force_draft'
    force_draft = StateTransition()

    def transition_force_draft(self):
        pool = Pool()
        Dunning = pool.get('account.dunning')
        Mails = pool.get('account.dunning.email.log')
        ids_ = Transaction().context['active_ids']
        for id_ in ids_:
            dunning = Dunning(id_)
            dunningTable = Dunning.__table__()
            #Validacion para saber si el activo se encuentra cerrado
            # if dunning.state == 'final':
            #     raise UserError('AVISO', f'La reclamacion id {dunning.id} se encuentra en estado final')
            #Validacion para saber si el activo ya se encuentra en borrador
            if dunning.state == 'draft':
                return 'end'
            cursor = Transaction().connection.cursor()
            #Consulta que le asigna el estado borrado al activo
            if id_:

                emails_delete = Mails.search([('dunning', '=', id_)])
                if emails_delete:
                    Mails.delete(emails_delete)

                cursor.execute(*dunningTable.update(
                    columns=[
                        dunningTable.state,
                    ],
                    values=["draft"],
                    where=dunningTable.id == id_)
                )
            
        return 'end'