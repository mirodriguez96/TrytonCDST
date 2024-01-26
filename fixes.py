from trytond.pool import Pool
from trytond.transaction import Transaction
from sql import Table
from trytond.exceptions import UserError

_SW = {
    '27': {
        'name': 'NOTA DEBITO COMPRAS',
        'type': 'in',
        'type_note': 'debit',
    },
    '28': {
        'name': 'NOTA CREDITO COMPRAS',
        'type': 'in',
        'type_note': 'credit',
    },
    '31': {
        'name': 'NOTA DEBITO',
        'type': 'out',
        'type_note': 'debit',
    },
    '32': {
        'name': 'NOTA CREDITO',
        'type': 'out',
        'type_note': 'credit',
    },
}

# def borrar_notas_de_adjuste(ids_ = None,id_tecno = None):
#     pool = Pool()
#     Actualizacion = pool.get('conector.actualizacion')
#     actualizacion = Actualizacion.create_or_update('ELIMINAR NOTAS DE AJUSTE')
#     logs = {}
#     exceptions = []
#     if ids_ is None:
#         raise UserError(f"No se ha ingresado ningun valor en el campos de ids")

#     if id_tecno == None:
#         number = ids_.split(',')
#         ids_ = [int(value) for value in number]
#     else:
#         ids_ = [id_tecno]

#     if ids_:
#         Dunning = pool.get('account.dunning')
#         Invoice = pool.get('account.invoice')
#         Sale = pool.get('sale.sale')
#         Purchase = pool.get('purchase.purchase')
#         Reclamacion = pool.get('account.dunning')
#         cursor = Transaction().connection.cursor()
#         to_delete_sales = []
#         to_delete_purchases = []
#         to_delete_note = []
#         for invoice in Invoice.browse(ids_):
#             if invoice.move.period.state == 'close':
#                 exceptions.append(id_tecno)
#                 logs[id_tecno] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
#                 Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"
#                 continue
#             reclamacion, = Reclamacion.search([('line.move.origin', '=', invoice)])
#             rec_name = invoice.rec_name
#             party_name = invoice.party.name
#             rec_party = rec_name+' de '+party_name
#             if invoice.number and '-' in invoice.number:
#                 if invoice.id_tecno:
#                     sw = invoice.id_tecno.split('-')[0]
#                     if sw in _SW.keys():
#                         to_delete_note.append(invoice)
#                         continue
#                 if invoice.type == 'out':
#                     sale = Sale.search([('number', '=', invoice.number)])
#                     if sale:
#                         to_delete_sales.append(sale[0])
#                 elif invoice.type == 'in':
#                     purchase = Purchase.search([('number', '=', invoice.number)])
#                     if purchase:
#                         to_delete_purchases.append(purchase[0])
#                 if reclamacion:
#                     dunningTable = Dunning.__table__()
#                     if reclamacion.state != 'draft':
#                         cursor.execute(*dunningTable.update(
#                             columns=[
#                                 dunningTable.state,
#                             ],
#                             values=["draft"],
#                             where=dunningTable.id == reclamacion.id)
#                         )
#                     cursor.execute(*dunningTable.delete(
#                         where=dunningTable.id == reclamacion.id)
#                     )
#         if to_delete_sales:
#             Sale.delete_imported_sales(to_delete_sales)
#         if to_delete_purchases:
#             Purchase.delete_imported_purchases(to_delete_purchases)
#         if to_delete_note:
#             Invoice.delete_imported_notes(to_delete_note)

#         actualizacion.add_logs(logs)
#         print("ELIMINAR NOTAS DE AJUSTE")


def eliminar_tecnocarnes_facturas(ids_=None, id_tecno=None):
    pool = Pool()
    Actualizacion = pool.get('conector.actualizacion')
    actualizacion = Actualizacion.create_or_update('ELIMINAR FACTURA')
    logs = {}
    exceptions = []
    if ids_ is None:
        raise UserError(f"No se ha ingresado ningun valor en el campos de ids")

    if id_tecno == None:
        number = ids_.split(',')
        ids_ = [int(value) for value in number]
    else:
        ids_ = [id_tecno]

    if ids_:
        Dunning = pool.get('account.dunning')
        Invoice = pool.get('account.invoice')
        Sale = pool.get('sale.sale')
        Purchase = pool.get('purchase.purchase')
        Reclamacion = pool.get('account.dunning')
        cursor = Transaction().connection.cursor()
        to_delete_sales = []
        to_delete_purchases = []
        to_delete_note = []
        for invoice in Invoice.browse(ids_):
            if invoice.move.period.state == 'close':
                exceptions.append(invoice.reference)
                logs[
                    invoice.
                    reference] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                continue
            reclamacion, = Reclamacion.search([('line.move.origin', '=',
                                                invoice)])
            rec_name = invoice.rec_name
            party_name = invoice.party.name
            rec_party = rec_name + ' de ' + party_name
            if invoice.number and '-' in invoice.number:
                if invoice.id_tecno:
                    sw = invoice.id_tecno.split('-')[0]
                    if sw in _SW.keys():
                        to_delete_note.append(invoice)
                        continue
                if invoice.type == 'out':
                    sale = Sale.search([('number', '=', invoice.number)])
                    if sale:
                        to_delete_sales.append(sale[0])
                elif invoice.type == 'in':
                    purchase = Purchase.search([('number', '=', invoice.number)
                                                ])
                    if purchase:
                        to_delete_purchases.append(purchase[0])
                if reclamacion:
                    dunningTable = Dunning.__table__()
                    if reclamacion.state != 'draft':
                        cursor.execute(*dunningTable.update(
                            columns=[
                                dunningTable.state,
                            ],
                            values=["draft"],
                            where=dunningTable.id == reclamacion.id))
                    cursor.execute(*dunningTable.delete(
                        where=dunningTable.id == reclamacion.id))
        if to_delete_sales:
            Sale.delete_imported_sales(to_delete_sales)
        if to_delete_purchases:
            Purchase.delete_imported_purchases(to_delete_purchases)
        if to_delete_note:
            Invoice.delete_imported_notes(to_delete_note)

        actualizacion.add_logs(logs)
        print("ELIMINAR FACTURAS")


def desconciliar_borrar_asientos(ids_=None, id_tecno=None):
    pool = Pool()
    Actualizacion = pool.get('conector.actualizacion')
    actualizacion = Actualizacion.create_or_update('ELIMINAR MOVIMIENTOS')
    logs = {}
    exceptions = []
    if ids_ is None and id_tecno == None:
        raise UserError(f"No se ha ingresado ningun valor en el campos de ids")
    if id_tecno == None:
        number = ids_.split(',')
        ids_ = [int(value) for value in number]
    else:
        ids_ = list(id_tecno)

    if ids_:
        Move = Table('account_move')
        account_move = pool.get('account.move')
        cursor = Transaction().connection.cursor()
        moves = account_move.search([('id', 'in', ids_)])
        Reconciliation = pool.get('account.move.reconciliation')
        to_delete = []

        # moves = account_move.browse(ids_)
        for move in moves:
            for line in move.lines:
                print(line.credit, line.id, line.debit)
            if move.period.state == 'close':
                exceptions.append(move.id)
                logs[
                    move.
                    id] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                continue
            to_delete.append(move.id)
            reconciliations = [
                l.reconciliation for l in move.lines if l.reconciliation
            ]
            if reconciliations:
                Reconciliation.delete(reconciliations)

            # account_move.draft(to_delete)
            # account_move.delete(to_delete)

        if to_delete:
            cursor.execute(*Move.update(columns=[Move.state],
                                        values=['draft'],
                                        where=Move.id.in_(to_delete)))
            cursor.execute(*Move.delete(where=Move.id.in_(to_delete)))

        actualizacion.add_logs(logs)
        print("ELIMINAR MOVIMIENTOS")
