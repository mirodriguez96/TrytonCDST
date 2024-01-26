from trytond.model import fields
from trytond.pool import PoolMeta


class Company(metaclass=PoolMeta):
    __name__ = 'company.company'
    # Campos para la configuración del proveedor tecnologico para el envío de nómina
    url_supplier = fields.Char(
        'Url prod', help='https://{instancia}/{instancia}/api/{metodo}')
    auth_supplier = fields.Char('Auth', help='user:password')
    host_supplier = fields.Char('Host', help='Example: dev.dominio.com.co')
    supplier_code = fields.Char(
        'Code', help='Branch code configured in the supplier it')
    # Campos para la configuración del proveedor tecnologico para el envío de documentos soporte
    url_ds_itsupplier = fields.Char(
        'Url prod', help='https://{instancia}/{instancia}/api/{metodo}')
    auth_ds_itsupplier = fields.Char('Auth', help='user:password')
    host_ds_itsupplier = fields.Char('Host',
                                     help='Example: dev.dominio.com.co')
    itsupplier_code_ds = fields.Char(
        'Code', help='Branch code configured in the supplier it')
    itsupplier_billing_resolution = fields.Char(
        'Billing Resolution Number',
        help='Number configured in the supplier it')
    itsupplier_billing_resolution_note = fields.Char(
        'Adjustment Note Billing Resolution Number',
        help=
        'Number configured in the supplier it for adjustment note print format'
    )
    itsupplier_print_format = fields.Char(
        'Print Format Number', help='Number configured in the supplier it')
    itsupplier_print_format_note = fields.Char(
        'Adjustment Note Print Format',
        help=
        'Number configured in the supplier it for adjustment note print format'
    )
    itsupplier_email_ds = fields.Char(
        'Email support document',
        help='Email to send a copy of the supporting document')
