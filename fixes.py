from trytond.pool import Pool
from trytond.transaction import Transaction
from sql import Table
from trytond.exceptions import UserError
import time

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


def desconciliar_borrar_asientos(ids_=None):
    """Function to draft and delete account moves"""
    pool = Pool()
    users = pool.get('res.user')

    logs = {}
    exceptions = []

    if ids_ is None:
        raise UserError(f"No se ha ingresado ningun valor en el campos de ids")

    number = ids_.split(',')
    ids_ = [int(value) for value in number]

    if ids_:
        account_move = pool.get('account.move')
        moves = account_move.search([('id', 'in', ids_)])
        to_delete = []

        for move in moves:

            if move:
                if move.period.state == 'close':
                    exceptions.append(move.id)
                    logs[
                        move.
                        id] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE ENCUENTRA CERRADO \
                    Y NO ES POSIBLE SU ELIMINACION O MODIFICACION"

                    continue

                to_delete.append(move.id)

    with Transaction().set_user(1):
        context = users.get_preferences()

    try:
        with Transaction().set_context(context):
            draft_move(ids_)
        Transaction().commit()
        print("paso1")

        with Transaction().set_context(context):
            desconciliate_moves(ids_)
        Transaction().commit()
        print("paso2")

        with Transaction().set_context(context):
            delete_move_lines(ids_)
        Transaction().commit()
        print("paso 3")

        for ids in ids_:
            with Transaction().set_context(context):
                delete_move(ids)
            Transaction().commit()

        print("SCRIPT FINALIZADO")

    except Exception as e:
        print("SCRIPT SIN FINALIZAR")
        print(f"Error: {e}")


def draft_move(move_ids):
    """Function that change state to draft"""
    pool = Pool()
    account_moves = pool.get('account.move')

    for move_id in move_ids:
        account_move = account_moves.search([('id', '=', move_id)])
        if account_move:
            if account_move[0].state != "draft":
                account_moves.draft(move_ids)
                time.sleep(1)


def desconciliate_moves(move_ids):
    """Function to dele conciliations"""
    pool = Pool()
    account_moves = pool.get('account.move')
    reconciliations = pool.get('account.move.reconciliation')

    for move_id in move_ids:
        account_move = account_moves.search([('id', '=', move_id)])

        if account_move:
            for move in account_move:
                for lines in move.lines:
                    if lines.reconciliation:
                        reconciliations.delete([lines.reconciliation])
                    time.sleep(0.3)


def delete_move_lines(move_ids):
    """Function to delete account_move_lines"""
    pool = Pool()
    account_move_lines = pool.get('account.move.line')
    to_delete = []
    for move_id in move_ids:
        to_delete = []
        account_move_line = account_move_lines.search([('move', '=', move_id)])

        if account_move_line:
            for move_line in account_move_line:
                to_delete.append(move_line)

        account_move_lines.delete(to_delete)
        time.sleep(1)


def delete_move(move_id):
    """Function to delete account_move"""
    pool = Pool()
    account_moves = pool.get('account.move')
    try:
        account_move = account_moves.search([('id', '=', move_id)])
        print(move_id)
        if account_move:
            account_moves.delete(account_move)
            time.sleep(1)
    except Exception as error:
        print(f"error: {error}")
