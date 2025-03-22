from trytond.pool import Pool
from .metabase import MetabaseAccess, MetabaseConfiguration



def register():
    Pool.register(
        metabase.MetabaseConfiguration,
        metabase.MetabaseAccess,
        metabase.MetabaseAccessResGroup,  # Agregar aquí la clase intermedia
        module='metabase_cdst', type_='model'
    )
