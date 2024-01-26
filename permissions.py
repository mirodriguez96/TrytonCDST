from trytond.model import ModelSQL, ModelView, fields
from trytond.pyson import Eval, Not, Bool
from trytond.transaction import Transaction
from trytond.pool import Pool
from .exceptions import DuplicateUserPermission
from trytond.i18n import gettext


class Permissions(ModelSQL, ModelView):
    'Permissions'
    __name__ = 'conector.permissions'

    user = fields.Many2One('res.user', 'User', readonly=True)

    super_user = fields.Boolean('Permission_Asing',
                                states={'readonly': Not(Bool(Eval('user')))},
                                depends=['user'])

    user_permission = fields.Many2One(
        'res.user',
        'User',
        required=True,
        states={'readonly': Not(Bool(Eval('super_user')))},
        depends=['super_user'])

    action = fields.Many2Many(
        'res.user-ir.action.wizard',
        'user_permission',
        'wizard',
        'Permissions',
        states={'readonly': Not(Bool(Eval('super_user')))},
        depends=['super_user'])

    @classmethod
    def validate(cls, permission):
        super(Permissions, cls).validate(permission)
        for item in permission:
            item.check_Permissions()

    def check_Permissions(self):
        pool = Pool()
        Permission = pool.get('conector.permissions')
        if self.user_permission:
            permission = Permission.search([
                ('user', '=', self.user_permission),
            ])
            if len(permission) > 1:
                for valid in permission:
                    raise DuplicateUserPermission(
                        gettext('conector.permissions.msg_duplicate_user',
                                permission=valid.user))

    @staticmethod
    def default_user():
        if Transaction().user == 1:
            return Transaction().user
        return None


class LinePermissions(ModelSQL):
    "Res User - Ir Action Wizard"
    __name__ = "res.user-ir.action.wizard"
    _table = 'res_user_ir_action_wizard_rel'
    wizard = fields.Many2One('ir.action.wizard',
                             'Wizard',
                             ondelete='RESTRICT',
                             select=True,
                             required=True)

    user_permission = fields.Many2One('conector.permissions',
                                      'User permission',
                                      ondelete='CASCADE',
                                      select=True,
                                      required=True)
