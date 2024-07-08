from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta

from datetime import date, timedelta
from .exceptions import UserError
from trytond.i18n import gettext
import copy


class PortfolioStatusReport(metaclass=PoolMeta):
    'Portfolio Status Report'
    __name__ = 'collection.portfolio_status_report'

    @classmethod
    def get_domain_invoice(cls, data):
        domain = [
            ('company', '=', data['company']),
            ('type', '=', data['kind']),
        ]
        if data['category_party']:
            domain.append(('party.categories', 'in', data['category_party']))
        if data['payment_terms']:
            domain.append(('payment_term', 'in', data['payment_terms']))
        if data['date_to']:
            dom = [
                'OR',
                [
                    ('payment_lines.date', '>=', data['date_to']),
                    ('state', '=', 'paid'),
                ], ('state', '=', 'posted')
            ]
            domain.append(dom)
            domain.append(('invoice_date', '<=', data['date_to']))
        else:
            domain.append(('state', '=', 'posted')),
        return domain

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        Company = pool.get('company.company')
        Invoice = pool.get('account.invoice')
        Line = pool.get('account.move.line')
        company = Company(data['company'])
        table = Line.__table_handler__('account_move_line')

        column_add = ''
        group_by_add = ''
        join_add = ''
        if table.column_exist('operation_center'):
            column_add = ", CONCAT(op.code, ' - ', op.name) as operation_center"
            group_by_add = ', op.code, op.name'
            join_add = 'LEFT JOIN company_operation_center AS op ON op.id = ml.operation_center'

        dom_invoices = cls.get_domain_invoice(data)
        if data['procedures']:
            accounts = []
            Procedure = pool.get('collection.procedure')
            procedures = Procedure.search_read(
                [('id', 'in', data['procedures'])], fields_names=['accounts'])
            for procedure in procedures:
                accounts.extend(list(procedure['accounts']))
            if not accounts:
                raise UserError(
                    gettext('collection.msg_missing_account_procedure'))
            dom_invoices.append(['account', 'in', accounts])
        order = [('party.name', 'DESC'), ('invoice_date', 'ASC')]
        invoices = Invoice.search(dom_invoices, order=order)
        records = {}
        today = date.today()
        deepcopy = copy.deepcopy
        expired_kind = {
            'range_0': [],
            'range_1_30': [],
            'range_31_60': [],
            'range_61_90': [],
            'range_91': [],
        }
        expired_sums = deepcopy(expired_kind)
        expired_sums['total'] = []
        move_ids = []
        append_move_ids = move_ids.append

        for invoice in invoices:
            if invoice.move:
                append_move_ids(invoice.move.id)
            if data['detailed']:
                key_id = str(invoice.party.id) + '_' + str(invoice.id)
            else:
                key_id = str(invoice.party.id)

            if key_id not in records.keys():
                _expired_kind = deepcopy(expired_kind)
                categories = invoice.party.categories
                records[key_id] = {
                    'party': invoice.party,
                    'category': categories[0].name if categories else '',
                    'total': [],
                    'notes': '',
                    'invoice': [],
                    'expired_days': '',
                }
                records[key_id].update(_expired_kind)

            time_forward = 0
            if data['date_to']:
                maturity_date = None
                move_lines_paid = []
                pay_to_date = []
                pay_append = pay_to_date.append
                line_append = move_lines_paid.append

                for line in invoice.payment_lines:
                    if line.move.date <= data['date_to']:
                        pay_append(line.debit - line.credit)
                        line_append(line.id)
                    else:
                        # if line.maturity_date and line.maturity_date < maturity_date or maturity_date is None: fix
                        if line.maturity_date and (maturity_date is None
                                                   or line.maturity_date
                                                   < maturity_date):
                            maturity_date = line.maturity_date

                if invoice.move:
                    for line in invoice.move.lines:
                        line_id = line.id
                        if not line.reconciliation:
                            continue
                        for recline in line.reconciliation.lines:
                            if recline.id == line_id or line_id in move_lines_paid:
                                continue
                            if recline.move.date <= data['date_to']:
                                pay_append(recline.debit - recline.credit)

                amount_paid = sum(pay_to_date)
                if not maturity_date:
                    maturity_date = invoice.estimate_pay_date or invoice.invoice_date

                time_forward = (data['date_to'] - maturity_date).days
                amount = invoice.total_amount - amount_paid
            else:
                amount = invoice.amount_to_pay
                if invoice.estimate_pay_date:
                    time_forward = (today - invoice.estimate_pay_date).days

            if time_forward <= 0:
                expire_time = 'range_0'
            elif time_forward <= 30:
                expire_time = 'range_1_30'
            elif time_forward <= 60:
                expire_time = 'range_31_60'
            elif time_forward <= 90:
                expire_time = 'range_61_90'
            else:
                expire_time = 'range_91'

            notes = None
            if hasattr(invoice, 'agent') and invoice.agent:
                notes = invoice.agent.rec_name
            if notes and not records[key_id]['notes']:
                records[key_id]['notes'] = notes

            records[key_id][expire_time].append(amount)
            records[key_id]['invoice'].append(invoice)
            records[key_id]['expired_days'] = time_forward
            records[key_id]['total'].append(amount)
            expired_sums[expire_time].append(amount)
            expired_sums['total'].append(amount)

        move_lines_without_invoice = {}
        if data['detailed']:
            cond1 = 'where'
            if data['category_party']:
                cat_ids = str(tuple(data['category_party'])).replace(
                    ',', '') if len(data['category_party']) == 1 else str(
                        tuple(data['category_party']))
                cond1 = f'''where pcr.category in %s and''' % (cat_ids)

            cond2 = ''
            if move_ids:
                cond2 = 'and ml.id not in %s' % (str(tuple(move_ids)).replace(
                    ',', '') if len(move_ids) == 1 else str(tuple(move_ids)))

            cond3 = ''
            if data['date_to']:
                cond3 = ' and am.date <= %s' % (
                    data['date_to'].strftime("'%Y-%m-%d'"))
            cond4 = ''
            if data['procedures']:
                cond4 = ' and ml.account in %s' % (str(
                    tuple(accounts)).replace(',', '') if len(accounts) == 1
                    else str(tuple(accounts)))
            type_ = 'receivable'
            if data['kind'] == 'in':
                type_ = 'payable'

            cursor = Transaction().connection.cursor()
            query = f"""SELECT ml.id, ml.move, pp.name, pc.name AS category {column_add}, pp.id_number, ml.description, ml.reference, am.date, am.number, ml.maturity_date, ac.code, (current_date-ml.maturity_date::date) AS expired_days, COALESCE(sum(av.amount), 0) AS payment_amount,
                CASE WHEN (current_date-ml.maturity_date::date)<=0
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_0,
                CASE WHEN (current_date-ml.maturity_date::date)<=30 AND (current_date-ml.maturity_date::date) > 0
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_1_30,
                CASE WHEN (current_date-ml.maturity_date::date)<=60 AND (current_date-ml.maturity_date::date) > 30
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_31_60,
                CASE WHEN (current_date-ml.maturity_date::date)<=90 AND (current_date-ml.maturity_date::date) > 60
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_61_90,
                CASE WHEN (current_date-ml.maturity_date::date)>90
                THEN (ml.debit-ml.credit) - COALESCE(sum(av.amount), 0) ELSE 0
                END AS range_91,
                ((ml.debit-ml.credit) - COALESCE(sum(av.amount), 0)) AS total
                from account_move_line AS ml
                LEFT JOIN account_account AS ac
                ON ml.account = ac.id LEFT JOIN account_account_type AS at
                ON ac.type = at.id LEFT JOIN account_voucher_line AS av
                ON ml.id=av.move_line LEFT JOIN account_move AS am
                ON am.id=ml.move LEFT JOIN party_party AS pp
                ON pp.id=ml.party LEFT JOIN (SELECT DISTINCT ON (party) party, category from party_category_rel) AS pcr
                ON pcr.party=pp.id LEFT JOIN party_category AS pc
                ON pcr.category=pc.id
                {join_add}
                %s at.{type_}='t' AND ac.reconcile='t' AND ml.maturity_date is not null AND am.origin is null AND ml.reconciliation is null
                %s %s %s
            group by ml.id, ml.move, pp.name, pc.name {group_by_add}, pp.id_number, ml.description, ml.reference, am.date, am.number, ml.maturity_date, ac.code, expired_days, ml.debit, ml.credit;""" % (
                cond1, cond2, cond3, cond4)
            cursor.execute(query)
            columns = list(cursor.description)
            result = cursor.fetchall()

            for row in result:
                row_dict = {}
                for i, col in enumerate(columns):
                    try:
                        expired_sums[col.name].append(row[i])
                    except Exception as error:
                        print(error)
                        pass
                    row_dict[col.name] = row[i]
                move_lines_without_invoice[row[0]] = row_dict

        lines_without_inv = move_lines_without_invoice.values()
        report_context['lines_without_inv'] = lines_without_inv
        report_context.update(expired_sums)
        report_context['records'] = records.values()
        report_context['company'] = company.party.name
        return report_context


class Tracking(metaclass=PoolMeta):
    'Tracking'
    __name__ = 'collection.tracking'

    def get_state(self, name):
        pool = Pool()
        Configuration = pool.get('collection.configuration')
        Date = pool.get('ir.date')
        try:
            configuration = Configuration(1)
        except Exception as error:
            print(error)
            raise UserError('ERROR', 'No hay configuracion')

        if configuration:
            _date = self.date + \
                timedelta(days=configuration.tracking_days_expired)
            if _date > Date.today():
                return 'active'
            # validate states please
            if self.collection_amount and self.collection_amount > 0:
                return 'done'
            else:
                return 'inactive'
