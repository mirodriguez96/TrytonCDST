
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from itertools import groupby


class Subscription(metaclass=PoolMeta):
    "Subscription"
    __name__ = 'sale.subscription'

    @classmethod
    def generate_invoice(cls, date=None):
        pool = Pool()
        Date = pool.get('ir.date')
        Consumption = pool.get('sale.subscription.line.consumption')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')

        if date is None:
            date = Date.today()
        company_id = Transaction().context.get('company', -1)

        consumptions = Consumption.search([
                ('invoice_line', '=', None),
                ('line.subscription.next_invoice_date', '<=', date),
                ('line.subscription.state', 'in', ['running', 'closed']),
                ('line.subscription.company', '=', company_id),
                ],
            order=[
                ('line.subscription.id', 'DESC'),
                ])

        def keyfunc(consumption):
            return consumption.line.subscription
        invoices = {}
        lines = {}
        for subscription, consumptions in groupby(consumptions, key=keyfunc):
            invoices[subscription] = invoice = subscription._get_invoice()
            lines[subscription] = Consumption.get_invoice_lines(
                consumptions, invoice)

        all_invoices = list(invoices.values())
        Invoice.save(all_invoices)

        all_invoice_lines = []
        for subscription, invoice in invoices.items():
            invoice_lines, _ = lines[subscription]
            for line in invoice_lines:
                line.invoice = invoice
                line.operation_center = 1
            all_invoice_lines.extend(invoice_lines)
        InvoiceLine.save(all_invoice_lines)

        all_consumptions = []
        for values in lines.values():
            for invoice_line, consumptions in zip(*values):
                for consumption in consumptions:
                    assert not consumption.invoice_line
                    consumption.invoice_line = invoice_line
                    all_consumptions.append(consumption)
        Consumption.save(all_consumptions)

        Invoice.update_taxes(all_invoices)

        subscriptions = cls.search([
                ('next_invoice_date', '<=', date),
                ('company', '=', company_id),
                ])
        for subscription in subscriptions:
            if subscription.state == 'running':
                while subscription.next_invoice_date <= date:
                    subscription.next_invoice_date = (
                        subscription.compute_next_invoice_date())
            else:
                subscription.next_invoice_date = None
        cls.save(subscriptions)
