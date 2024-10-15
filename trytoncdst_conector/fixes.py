from trytond.exceptions import UserError
from trytond.pool import Pool
from trytond.transaction import Transaction

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


def eliminar_tecnocarnes_facturas(ids_=None, id_tecno=None):
    pool = Pool()
    Actualizacion = pool.get('conector.actualizacion')
    actualizacion = Actualizacion.create_or_update('ELIMINAR FACTURA')
    logs = {}
    exceptions = []

    if ids_ is None:
        raise UserError("No se ha ingresado ningun valor en el campos de ids")

    if not id_tecno:
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
                    reference] = "EXCEPCION: EL PERIODO DEL DOCUMENTO SE "\
                    "ENCUENTRA CERRADO Y NO ES POSIBLE SU ELIMINACION"\
                    " O MODIFICACION"

                continue
            reclamacion, = Reclamacion.search([('line.move.origin', '=',
                                                invoice)])
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


def draft_unconciliate_delete_account_move(ids_=None, action=None):
    """Function to draft and delete account moves"""
    pool = Pool()
    User = pool.get('res.user')

    logs = {}
    exceptions = []

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
                        id] = "EXCEPCION: EL PERIODO DEL DOCUMENTO "\
                        "SE ENCUENTRA CERRADO Y NO ES POSIBLE SU "\
                        "ELIMINACION O MODIFICACION"

                    continue

                to_delete.append(move.id)

    with Transaction().set_user(1):
        context = User.get_preferences()

        try:
            if action == "draft":
                draft_move(to_delete, context)
            elif action == "unconciliate":
                delete_conciliations(to_delete, context)
            else:
                delete_move(to_delete, context)
        except Exception as e:
            print(f"Error: {e}")

    return True


def draft_move(to_delete, context):
    """Function that change state to draft"""
    pool = Pool()
    AccountMove = pool.get('account.move')
    with Transaction().set_context(context):
        to_draft = []
        for move_id in to_delete:
            account_move = AccountMove.search([('id', '=', move_id)])
            if account_move:
                to_draft.append(move_id)
                print('forzando a borrador')
        AccountMove.draft(to_draft)
    Transaction().commit()

    return True


def delete_conciliations(move_ids, context):
    """Function to unreconcilie account moves"""
    pool = Pool()
    Reconciliation = pool.get('account.move.reconciliation')
    Move = pool.get('account.move')

    with Transaction().set_context(context):
        moves = Move.browse(move_ids)
        print(f'movimiento {moves}')
        if moves:
            for move in moves:
                reconciliations = [
                    lines.reconciliation.id for lines in move.lines
                    if lines.reconciliation
                ]

                if reconciliations:
                    records = Reconciliation.browse(reconciliations)
                    Reconciliation.delete(records, conector=True)
                reconciliations = []
    Transaction().commit()

    return True


def delete_move(to_delete, context):
    """Function to delete account_move"""
    pool = Pool()
    AccountMove = pool.get('account.move')

    for move_id in to_delete:
        try:
            account_move = AccountMove.search([('id', '=', move_id)])
            if account_move:
                print(f"Eliminando cuenta {move_id}")
                AccountMove.delete_lines(account_move)
        except Exception as error:
            print(f"error: {error}")

    return True
