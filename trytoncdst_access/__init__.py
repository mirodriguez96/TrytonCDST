from trytond.pool import Pool

__all__ = ['register']

from . import access


def register():
    Pool.register(
        access.CreateAccessHolidaysView,
        access.StaffAccessRests,
        access.StaffAccess,
        access.ImportBiometricRecordsParameters,
        access.StaffAccessView,
        module='access', type_='model')

    Pool.register(
        access.CreateAccessHolidaysWizard,
        access.ImportBiometricRecords,
        access.StaffAccessWizard,
        module='access', type_='wizard')

    Pool.register(
        access.StaffAccessReport,
        module='access', type_='report')
