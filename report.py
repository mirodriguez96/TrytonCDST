from trytond.report import Report
from trytond.wizard import Wizard, StateView, Button, StateReport
from datetime import datetime, date, time
from decimal import Decimal
from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
from sql.aggregate import Sum
from .constants import (ENTITY_ACCOUNTS)

_ZERO = Decimal(0)

# REPORTE DE NOMINA MODIFICADO
class PayrollExportStart(ModelView):
    'Export Payroll Start'
    __name__ = 'report.payroll.export.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    start_period = fields.Many2One('staff.payroll.period', 'Start Period',
                                   required=True)
    end_period = fields.Many2One('staff.payroll.period', 'End Period',
                                 required=True)
    department = fields.Many2One('company.department', 'Department',
                                 required=False, depends=['employee'])

    @staticmethod
    def default_company():
        return Transaction().context.get('company')


class PayrollExport(Wizard):
    'Payroll Export'
    __name__ = 'report.payroll.export'
    start = StateView('report.payroll.export.start',
                      'conector.payroll_export_start_view_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                          ])
    print_ = StateReport('report.payroll.export_report')

    def do_print_(self, action):
        department_id = self.start.department.id \
            if self.start.department else None
        data = {
            'ids': [],
            'company': self.start.company.id,
            'start_period': self.start.start_period.id,
            'end_period': self.start.end_period.id,
            'department_id': department_id,
        }
        return action, data

    def transition_print_(self):
        return 'end'


class PayrollExportReport(Report):
    __name__ = 'report.payroll.export_report'

    @classmethod
    def get_domain_payroll(cls, data=None):
        dom_payroll = []

        return dom_payroll

    @classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        company = pool.get('company.company')(data['company'])
        Payroll = pool.get('staff.payroll')
        Period = pool.get('staff.payroll.period')
        dom_payroll = cls.get_domain_payroll()
        start_period, = Period.search([('id', '=', data['start_period'])])
        end_period, = Period.search([('id', '=', data['end_period'])])
        dom_payroll.append([
            ('period.start', '>=', start_period.start),
            ('period.end', '<=', end_period.end),
            ('move', '!=', None)
        ])
        if data['department_id'] not in (None, ''):
            dom_payroll.append([
                ('employee.department', '=', data['department_id'])
            ])

        payrolls = Payroll.search(dom_payroll, order=[('period.name', 'ASC')])
        records = {}
        for payroll in payrolls:
            employee = payroll.employee
            """ extract debit account and party mandatory_wages"""
            accdb_party = {mw.wage_type.debit_account.id: mw.party
                           for mw in employee.mandatory_wages
                           if mw.wage_type.debit_account and mw.party}
            move = payroll.move
            accountdb_ids = accdb_party.keys()
            for line in move.lines:
                """Check account code in dict account debit and party"""
                if not line.party:
                    continue
                line_ = {
                    'date': line.move.date,
                    'code': '---',
                    'party': employee.party.id_number,
                    'name': employee.party.name,
                    'description': line.description,
                    'department': employee.department.name if employee.department else '---',
                    'amount': line.debit or line.credit,
                    'type': 'D',
                }
                if line.debit > 0:
                    if line.account.id in accountdb_ids:
                        id_number = accdb_party[line.account.id].id_number
                    else:
                        id_number = None

                    if id_number in ENTITY_ACCOUNTS.keys():
                        line_['code'] = ENTITY_ACCOUNTS[id_number][1]
                    else:
                        line_['code'] = line.account.code

                else:
                    line_['type'] = 'C'
                    id_number = line.party.id_number
                    if id_number in ENTITY_ACCOUNTS.keys():
                        line_['code'] = ENTITY_ACCOUNTS[id_number][0]
                    else:
                        line_['code'] = line.account.code

                if line.account.code not in records.keys():
                    records[line.account.code] = {
                        'name': line.account.name,
                        'lines': []
                        }
                records[line.account.code]['lines'].append(line_)

        report_context['records'] = records
        report_context['start_date'] = start_period.name
        report_context['end_date'] = end_period.name
        report_context['company'] = company.party.name
        return report_context

class CDSSaleIncomeDailyStart(ModelView):
    'CDSSale Income Daily Start'
    __name__ = 'sale_pos.cdssale_income_daily.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    date = fields.Date('Date', required=True)
    shop = fields.Many2One('sale.shop', 'Shop')
    user = fields.Many2One('res.user', 'User')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @staticmethod
    def default_shop():
        return Transaction().context.get('shop')

    @staticmethod
    def default_user():
        return Transaction().user

    @staticmethod
    def default_date():
        Date = Pool().get('ir.date')
        return Date.today()

class CDSSaleIncomeDaily(Wizard):
    'CDSSale Income Daily'
    __name__ = 'sale_pos.cdssale_income_daily'
    start = StateView('sale_pos.cdssale_income_daily.start',
        'conector.cdssale_income_daily_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
            ])
    print_ = StateReport('sale_pos.cdssale_income_daily_report')

    def do_print_(self, action):
        shop_id, user_id = None, None
        if self.start.user:
            user_id = self.start.user.id
        if self.start.shop:
            shop_id = self.start.shop.id
        report_context = {
            'company': self.start.company.id,
            'date': self.start.date,
            'user': user_id,
            'shop': shop_id,
        }
        return action, report_context

    def transition_print_(self):
        return 'end'

class CDSSaleIncomeDailyReport(Report):
    'CDSIncome Daily Report'
    __name__ = 'sale_pos.cdssale_income_daily_report'

    @classmethod
    def get_query(cls, data, products_exception):
        pool = Pool()
        Sale = pool.get('sale.sale')
        Line = pool.get('sale.line')
        Invoice = pool.get('account.invoice')
        fixed_hour = time(6, 0)    

        cursor = Transaction().connection.cursor()
        sale = Sale.__table__()
        line = Line.__table__()
        result_ = {}
        where_ = sale.state.in_(['processing', 'done'])
        where_ = line.product.in_(products_exception)
        where_ &= sale.company == data['company']
        where_ &= sale.invoice_type == 'P'
        where_ &= sale.number != Null
        if data['shop']:
            where_ &= sale.shop == data['shop']

        where_ &= sale.invoice_date == data['sale_date']
        columns_ = [sale.id, Sum(line.unit_price*line.quantity).as_('amount')]
        query = line.join(sale, condition=line.sale==sale.id).select(*columns_,
                where=where_,
                group_by=sale.id)

        cursor.execute(*query)
        columns = list(cursor.description)
        result = cursor.fetchall()
        for row in result:
            result_[row[0]] = row[1]
        return result_

    @classmethod
    def get_context(cls, registros, header, data):
        report_context = super().get_context(registros, header, data)
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Voucher = pool.get('account.voucher')
        Company = pool.get('company.company')
        company = Company(data['company'])
        Statement = pool.get('account.statement')
        Shop = pool.get('sale.shop')
        User = pool.get('res.user')
        Sale = pool.get('sale.sale')
        registros = []
        dispositivo = []
        statements_ = {}
        advances = []
        total_advances = []
        advances_cash = []
        advances_electronic = []
        total_statements = []
        statement_cash = []
        statement_electronic = []
        advances_voucher = []
        totality_payments= []
        pagos = []
        payments_voucher = []
        payments_cash = []
        payments_electronic = []

        dom_statement = [
            ('date', '=', data['date']),
        ]
        if data['shop']:
            dom_statement.append(('sale_device.shop.id', '=', data['shop']))
        statements = Statement.search(dom_statement)
        user_id = Transaction().user
        user = User(user_id)

        for statement in statements:
            st_amount = sum(l.amount for l in statement.lines)
            to_add = {
                'journal': statement.journal.name,
                'turn': statement.turn,
                'total_amount': st_amount,
            }
            if statement.sale_device.id not in statements_.keys():
                statements_[statement.sale_device.id] = {
                    'name': statement.sale_device.name,
                    'total': [st_amount],
                    'records': [to_add]
                }
            else:
                statements_[statement.sale_device.id]['total'].append(st_amount)
                statements_[statement.sale_device.id]['records'].append(to_add)
            total_statements.append(st_amount)

            for l in statement.lines:
                if l.statement.journal.kind == 'cash':
                    statement_cash.append(l.amount)
                else:
                    statement_electronic.append(l.amount)


        dom_vouchers = [
            ('move', '!=', None),
            ('date', '=', data['date']),
        ]
        if data['user']:
            dom_vouchers.append(
                ('create_uid', '=', data['user']),
            )
        vouchers = Voucher.search(dom_vouchers)
        for v in vouchers:
            cash = 0
            electronic = 0
            for l in v.lines:
                if v.voucher_type == 'receipt':
                    if v.payment_mode.payment_type == 'cash':
                        advances_cash.append(l.amount)
                        cash = l.amount
                    else:
                        advances_electronic.append(l.amount)
                        electronic = l.amount
                    advances_voucher.append(l.amount)
                    advances.append({
                        'number': l.voucher.number,
                        'reference': l.detail,
                        'party': l.party.name if l.party else l.voucher.party.name,
                        'total_amount': l.amount,
                        'payment_mode': l.voucher.payment_mode.name,
                        'cash': cash,
                        'electronic': electronic,
                    })
                    total_advances.append(l.amount)
                if v.voucher_type == 'payment':
                    amount_ = l.amount * (-1)
                    if v.payment_mode.payment_type == 'cash':
                        payments_cash.append(amount_)
                        cash = amount_
                    else:
                        payments_electronic.append(amount_)
                        electronic = amount_
                    payments_voucher.append(amount_)
                    pagos.append({
                        'number': l.voucher.number,
                        'reference': l.detail,
                        'party': l.party.name if l.party else l.voucher.party.name,
                        'total_amount': amount_,
                        'payment_mode': l.voucher.payment_mode.name,
                        'cash': cash,
                        'electronic': electronic,
                    })
                    totality_payments.append(amount_)

        dom_invoices = [
            ('company', '=', data['company']),
            ('invoice_date', '=', data['date']),
            ('number', '!=', None),
            ('state', 'in', ['posted', 'paid', 'validated']),
        ]
        shop_names = ''
        if data['shop']:
            shop_names = Shop(data['shop']).name
            dom_invoices.append(
                ('shop', '=', data['shop'])
            )
        else:
            shops = Shop.search([])
            for s in shops:
                shop_names += s.name + ', '

        invoices = Invoice.search(dom_invoices, order=[('number', 'ASC')])
        invoices_number = []
        total_invoices_cash = []
        total_invoices_electronic = []
        total_invoices_credit = []
        total_invoices_paid = []
        dispositivo = {}
        total_invoices_amount = []

        for invoice in invoices:
            invoices_number.append(invoice.number)
            cash = 0
            electronic = 0
            credit = 0
            paid = 0
            total_invoices_amount.append(invoice.total_amount)
            sale_device_name = 'NO TERMINAL'
            device_id = 'ELECTRONIC'
            if invoice.sales:
                sale = invoice.sales[0]
                if sale.sale_device:
                    device_id = sale.sale_device.id
                    sale_device_name = sale.sale_device.name
                else:
                    device_id = 'ELECTRONIC'
                    sale_device_name = 'NO TERMINAL'
                if not sale.payments:
                    total_invoices_credit.append(invoice.amount_to_pay)
                    credit = invoice.amount_to_pay
                else:
                    for p in sale.payments:
                        if p.statement.date == data['date']:
                            if p.statement.journal.kind == 'cash':
                                cash += p.amount
                                total_invoices_cash.append(p.amount)
                            else:
                                electronic += p.amount
                                total_invoices_electronic.append(p.amount)
                            total_invoices_paid.append(p.amount)
                paid = cash + electronic

            inv = {
                'number': invoice.number,
                'reference': invoice.reference,
                'party': invoice.party.name,
                'total_amount': invoice.total_amount,
                'credit': credit,
                'cash': cash,
                'electronic': electronic,
                'paid': paid,
                'state': invoice.state_string,
                'sale_device': sale_device_name,
            }
            registros.append(inv)
            try:
                dispositivo[device_id]['total'].append(invoice.total_amount)
                dispositivo[device_id]['cash'].append(cash)
                dispositivo[device_id]['electronic'].append(electronic)
                dispositivo[device_id]['credit'].append(credit)
                dispositivo[device_id]['paid'].append(paid)
            except:
                dispositivo[device_id] = {
                    'name': sale_device_name,
                    'total': [invoice.total_amount],
                    'credit': [credit],
                    'cash': [cash],
                    'electronic': [electronic],
                    'paid': [paid],
                }

        advances_cash_ = sum(advances_cash)
        advances_electronic_ = sum(advances_electronic)
        statement_cash_ = sum(statement_cash)
        statement_electronic_ = sum(statement_electronic)
        payments_cash_ = sum(payments_cash)
        payments_electronic_ = sum(payments_electronic)

        pool = Pool()
        Sale = pool.get('sale.sale')
        Company = pool.get('company.company')
        company = Company(data['company'])
        Shop = pool.get('sale.shop')
        Tax = pool.get('account.tax')
        Device = pool.get('sale.device')
        fixed_hour = time(6, 0)

        config = pool.get('sale.configuration')(1)
        products_exception = []
        amount_exception = {}
        if hasattr(config, 'tip_product') and config.tip_product and config.exclude_tip_and_delivery:
            products_exception.append(config.tip_product.id)
            if hasattr(config, 'delivery_product') and config.delivery_product and config.exclude_tip_and_delivery:
                products_exception.append(config.delivery_product.id)

        if products_exception:
            amount_exception = cls.get_query(data, products_exception)

        if data['shop']:
            dom_sales = [
                ('shop', '=', data['shop']),
                ('company', '=', data['company']),
                ('number', '!=', None),
            ]
        else:
            dom_sales = [
                ('company', '=', data['company']),
                ('number', '!=', None),
                ('sale_date', '=', data['date']),
            ]

        states_sale = ['processing', 'done']
        dom_sales.append(('state', 'in', states_sale))

        sales = Sale.search(dom_sales, order=[('number', 'ASC')])

        untaxed_amount = []
        tax_amount = []
        total_amount = []

        devices_ = Device.search([])
        
        devices = {}
        for d in devices_:
            devices[d.id] = {
                'name': d.name,
                'code': d.code,
                'count_invoices': 0,
                'untaxed_amount': [],
                'tax_amount': [],
                'total_amount': [],
                'cash': [],
                'credit': [],
                'electronic': [],
                'other': [],
                'number':'1',
                'party':'orcio',
            }
        
        devices['Venta Electronica'] = {
                'name': 'Venta Electronica',
                'code': 'Venta Electronica',
                'count_invoices': 0,
                'untaxed_amount': [],
                'tax_amount': [],
                'total_amount': [],
                'cash': [],
                'credit': [],
                'electronic': [],
                'other': [],
                'number':'1',
                'party':'orcio',
            }

        payment_modes = {
            'cash': [],
            'credit': [],
            'electronic': [],
            'other': [],
        }
        numbers = []
        categories = {}
        discounts = {}
        _payments = {}
        total_discount = []
        total_payments = []
        for sale in sales:
            payments = sale.payments
            sale_id = sale.id
            device_id = None
            try:
                value_except = Decimal(amount_exception[sale_id])
            except:
                value_except= Decimal(0)
            if sale.sale_device:
                device_id = sale.sale_device.id
            else:
                device_id = 'Venta Electronica'
            if sale.total_amount <= 0:
                continue

            if not sale.invoices:
                continue

            invoice = sale.invoices[0]
            if not invoice.number or invoice.total_amount <= 0 or not device_id:
                continue
            numbers.append(invoice.number)
            untaxed_ammount_ = invoice.untaxed_amount - value_except
            total_amount_ = invoice.total_amount - value_except

            devices[device_id]['count_invoices'] += 1
            devices[device_id]['untaxed_amount'].append(untaxed_ammount_)
            devices[device_id]['tax_amount'].append(invoice.tax_amount)
            devices[device_id]['total_amount'].append(total_amount_)

            untaxed_amount.append(untaxed_ammount_)
            tax_amount.append(invoice.tax_amount)
            total_amount.append(total_amount_)
            if payments:
                amount_by_sale = []
                for payment in payments:
                    kind = payment.statement.journal.kind
                    amount = payment.amount
                    if value_except > 0 and payment.amount > value_except:
                        amount = payment.amount - value_except
                        value_except = 0
                    amount_by_sale.append(amount)
                    if kind not in ['cash', 'credit', 'electronic']:
                        kind = 'other'

                    devices[device_id][kind].append(amount)
                    payment_modes[kind].append(amount)
                    journal = payment.statement.journal
                    try:
                        _payments[journal.id]['amount'].append(amount)
                    except:
                        _payments[journal.id] = {
                            'name': journal.name,
                            'amount': [amount],
                        }
                    total_payments.append(amount)

                amount_to_pay = invoice.amount_to_pay
                if amount_to_pay > 0:
                    # THIS MUST WORKS IN FUTURE WITH ADD PAYMENT INSTATEMENT TO INVOICE
                    # devices[device_id]['credit'].append(amount_to_pay)
                    # payment_modes['credit'].append(amount_to_pay)

                    # FIX TEMPORAL
                    inv_balance = invoice.total_amount - sum(amount_by_sale)
                    devices[device_id]['credit'].append(inv_balance)
                    payment_modes['credit'].append(inv_balance)
            else:
                if not sale.sale_device:
                    devices['Venta Electronica']['credit'].append(total_amount_)
                else:
                    devices[sale.sale_device.id]['credit'].append(total_amount_)
                if value_except > 0:
                    payment_modes['credit'].append(invoice.amount_to_pay - value_except)
                else:
                    payment_modes['credit'].append(invoice.amount_to_pay)

            for line in invoice.lines:
                category_id = '0'
                if line.product.id in products_exception:
                    continue
                if line.product.account_category:
                    category = line.product.account_category
                    category_id = category.id
                if category_id not in categories.keys():
                    categories[category_id] = {
                        'name': category.name,
                        'base': [line.amount],
                        'taxes': {},
                    }
                    if line.taxes and line.amount:
                        for t in line.taxes:
                            categories[category_id]['taxes'][t.id] = {
                                'tax': [t],
                                'base': [line.amount],
                            }
                else:
                    if line.taxes and line.amount:
                        for t in line.taxes:
                            try:
                                categories[category_id]['taxes'][t.id]['base'].append(line.amount)
                            except:
                                categories[category_id]['taxes'][t.id] = {
                                    'tax': [t],
                                    'base': [line.amount],
                                }
                    categories[category_id]['base'].append(line.amount)
                if line.discount:
                    try:
                        disc = line.amount / (1 - line.discount)
                    except:
                        disc = line.product.template.list_price * Decimal(line.quantity)
                    if category_id not in discounts.keys():
                        discounts[category_id] = {
                            'name': category.name,
                            'amount': [disc],
                        }
                    else:
                        discounts[category_id]['amount'].append(disc)
                    total_discount.append(disc)
        for k, v in categories.items():
            base = sum(v['base'])
            categories[k]['base'] = base
            taxes = categories[k]['taxes']
            if len(taxes) > 0:
                for t, m in categories[k]['taxes'].items():
                    tax_list = Tax.compute(m['tax'], sum(m['base']), 1)
                    categories[k]['taxes'][t].update({
                        'name': tax_list[0]['tax'].name,
                        'base': sum(m['base']),
                        'amount': tax_list[0]['amount']
                    })
            else:
                categories[k]['taxes'][0] = {
                    'name': 'EXCLUIDOS / EXENTOS',
                    'base': base,
                    'amount': _ZERO
                }
        if numbers:
            min_number = min(numbers)
            max_number = max(numbers)

        else:
            min_number = ''
            max_number = ''

        eliminar = []
        for i in devices.keys():
            if devices[i]['count_invoices'] == 0:
                eliminar.append(i)
        for e in eliminar:
             del devices[e]

        report_context['company'] = company.party
        report_context['start_number'] = min_number
        report_context['end_number'] = max_number
        report_context['records'] = devices.values()
        report_context['categories'] = categories.values()
        report_context['sum_count_invoices'] = len(numbers)
        report_context['sum_untaxed_amount'] = sum(untaxed_amount)
        report_context['sum_tax_amount'] = sum(tax_amount)
        report_context['sum_total_amount'] = sum(total_amount)
        report_context['discounts'] = discounts.values()
        report_context['total_discount'] = sum(total_discount)
        report_context['payments1'] = _payments.values()
        report_context['total_payments1'] = sum(total_payments)
        report_context['sum_cash'] = sum(payment_modes['cash'])
        report_context['sum_credit'] = sum(payment_modes['credit'])
        report_context['sum_electronic'] = sum(payment_modes['electronic'])
        report_context['sum_other'] = sum(payment_modes['other'])

        ########################################################################################################
        report_context['registros'] = registros
        report_context['devices'] = dispositivo.values()
        report_context['advances'] = advances
        report_context['statements'] = statements_.values()
        report_context['date'] = data['date']
        report_context['shop'] = shop_names
        report_context['user'] = user.name
        report_context['print_date'] = datetime.now()
        report_context['statement_cash'] = statement_cash_
        report_context['statement_electronic'] = statement_electronic_
        report_context['total_invoices_amount'] = sum(total_invoices_amount)
        report_context['total_invoices_cash'] = sum(total_invoices_cash)
        report_context['total_invoices_electronic'] = sum(total_invoices_electronic)
        report_context['total_invoices_credit'] = sum(total_invoices_credit)
        report_context['total_invoices_paid'] = sum(total_invoices_paid)
        report_context['total_advances'] = sum(total_advances)
        report_context['advances_cash'] = advances_cash_
        report_context['advances_electronic'] = advances_electronic_
        report_context['advances_voucher'] = sum(advances_voucher)
        report_context['total_statements'] = sum(total_statements)
        report_context['start_invoice'] = min(invoices_number) if invoices_number else ''
        report_context['end_invoice'] = max(invoices_number) if invoices_number else ''
        report_context['total_cash'] = advances_cash_ + statement_cash_
        report_context['total_electronic'] = advances_electronic_ + statement_electronic_
        report_context['total_payments'] = sum(totality_payments)
        report_context['payments_voucher'] = sum(payments_voucher)
        report_context['payments_cash'] = payments_cash_
        report_context['payments_electronic'] = payments_electronic_
        report_context['payments'] = pagos
        return report_context
