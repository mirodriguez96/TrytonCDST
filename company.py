from trytond.model import fields
from trytond.pool import PoolMeta


class Company(metaclass=PoolMeta):
    __name__ = 'company.company'
    url_supplier_test = fields.Char('Url test', help='https://{instancia}/{instancia}/api/{metodo}')
    url_supplier = fields.Char('Url prod', help='https://{instancia}/{instancia}/api/{metodo}')
    #auth_supplier_test = fields.Char('Auth', help='user:password')
    auth_supplier = fields.Char('Auth', help='user:password')
    #host_supplier_test = fields.Char('Host', help='Example: dev.dominio.com.co')
    host_supplier = fields.Char('Host', help='Example: dev.dominio.com.co')
    #supplier_code_test = fields.Char('Code', help='Branch code configured in the supplier it')
    supplier_code = fields.Char('Code', help='Branch code configured in the supplier it')
