from trytond.pool import Pool

import conector
#import wiz


def register():
    Pool.register(
        conector.Terceros,
        #wiz.CargarDatosParameters,
        module='conector', type_='model')

"""
    Pool.register(
        wiz.CargarDatos,
        module='mimporta', type_='wizard')
"""
