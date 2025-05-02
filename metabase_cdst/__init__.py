from trytond.pool import Pool
from .metabase import MetabaseAccess, MetabaseConfiguration, MetabaseAccessResGroup


def register():
    Pool.register(
        MetabaseConfiguration,
        MetabaseAccess,
        MetabaseAccessResGroup,  # Agregar aquí la clase intermedia
        module='metabase_cdst', type_='model'
    )
