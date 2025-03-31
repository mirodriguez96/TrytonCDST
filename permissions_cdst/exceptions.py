# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

from trytond.exceptions import UserError
from trytond.model.exceptions import ValidationError


class ImportDataEmployeeError(ValidationError):
    pass


class LiquidationEmployeeError(UserError):
    pass


class LiquidationDeleteError(UserError):
    pass


class RecordDuplicateError(UserError):
    pass


class NotificationEmail(UserWarning):
    pass


class MissingSecuenceCertificate(UserError):
    pass


class WageTypeConceptError(UserError):
    pass


class GeneratePayrollError(UserError):
    pass


class GeneratePayrollMoveError(UserError):
    pass


class MissingTemplateEmailPayroll(ValidationError):
    pass


class DuplicateUserPermission(ValidationError):
    pass

class NotMoveStatementeLine(ValidationError):
    pass