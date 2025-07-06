from trytond.pool import PoolMeta, Pool
from trytond.model import ModelView, ModelSQL, fields
from trytond.transaction import Transaction


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
        help='Number configured in the supplier it for adjustment note print format'
    )
    itsupplier_print_format = fields.Char(
        'Print Format Number', help='Number configured in the supplier it')
    itsupplier_print_format_note = fields.Char(
        'Adjustment Note Print Format',
        help='Number configured in the supplier it for adjustment note print format'
    )
    itsupplier_email_ds = fields.Char(
        'Email support document',
        help='Email to send a copy of the supporting document')


class Area(ModelSQL, ModelView):
    """Area model for company employees"""
    __name__ = 'employee.area'

    name_area = fields.Char('Name area', required=True, help='Example: Development')
    company = fields.Many2One('company.company', 'Company',
        required=True, help='Company to which the area belongs')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    def get_rec_name(self, name):
        return self.name_area


class Employee(metaclass=PoolMeta):
    __name__ = 'company.employee'

    area = fields.Many2One('employee.area', 'Area', required=True)
