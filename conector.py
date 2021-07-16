
from conexion import conexion
from trytond.model import ModelSQL, ModelView, fields
from trytond.pool import Pool
import datetime
import json

__all__ = [
    'Terceros',
    ]

class Terceros(ModelSQL, ModelView):
    'Terceros'
    __name__ = 'conector.terceros'

    actualizacion = fields.Char('Actualizacion', required=True)
    fecha = fields.DateTime('Fecha y hora', format="%H:%M:%S", required=True)


    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
                'cargar_datos': {},
                })

    """
    @classmethod
    def validate(cls, books):
        for book in books:
            if not book.isbn:
                continue
            try:
                if int(book.isbn) < 0:
                    raise ValueError
            except ValueError:
                cls.raise_user_error('invalid_isbn')
    """

    @classmethod
    def default_fecha(cls):
        return datetime.datetime.now()

    @classmethod
    @ModelView.button
    def cargar_datos(cls, fecha = None):
        
        #terceros = cls.carga_terceros()
        #cls.carga_productos()
        
        terceros_tecno = []
        columnas_terceros = []
        direcciones_tecno = []
        columna_direcciones = []

        try:
            with conexion.cursor() as cursor:
                #Datos de terceros
                querycol = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TblTerceros' ORDER BY ORDINAL_POSITION")
                for d in querycol.fetchall():
                    columnas_terceros.append(d[0])
                query = cursor.execute("SELECT TOP(5) * FROM dbo.TblTerceros")
                terceros_tecno = list(query.fetchall())
                #Datos de direcciones
                querycol2 = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Terceros_Dir' ORDER BY ORDINAL_POSITION")
                for d in querycol2.fetchall():
                    columna_direcciones.append(d[0])
                query2 = cursor.execute("SELECT TOP(5) * FROM dbo.Terceros_Dir")
                direcciones_tecno = list(query2.fetchall())
                cursor.close()
                conexion.close()
        except Exception as e:
            print("ERROR consulta terceros: ", e)

        pool = Pool()
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Lang = pool.get('ir.lang')
        es, = Lang.search([('code', '=', 'es')])
        Mcontact = pool.get('party.contact_mechanism')
        to_create = []
        for ter in terceros_tecno:
            tercero = Party()
            tercero.create_date = ter[columnas_terceros.index('fecha_creacion')]
            tercero.code = ter[columnas_terceros.index('nit_cedula')]
            tercero.name = ter[columnas_terceros.index('nombre')]
            tercero.write_date = ter[columnas_terceros.index('Ultimo_Cambio_Registro')]
            if ter[columnas_terceros.index('Ultimo_Cambio_Registro')] == 'Natural':
                tercero.type_person = 'persona_natural'
            else:
                tercero.type_person = 'persona_juridica'
            tercero.lang = es
            for dir in direcciones_tecno:
                if dir[columna_direcciones.index('nit')] == ter[columnas_terceros.index('nit_cedula')]:
                    if dir[columna_direcciones.index('telefono_1')]:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir[columna_direcciones.index('telefono_1')]
                        contacto.party = tercero
                        contacto.save()
                    if dir[columna_direcciones.index('telefono_2')]:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir[columna_direcciones.index('telefono_2')]
                        contacto.party = tercero
                        contacto.save()
                    if ter[columnas_terceros.index('mail')]:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'email'
                        contacto.value = ter[columnas_terceros.index('mail')]
                        contacto.party = tercero
                        contacto.save()
                    #Creacion e inserccion de direcciones
                    direccion = Address()
                    direccion.city = dir[columna_direcciones.index('ciudad')]
                    direccion.country = 50
                    direccion.name = dir[columna_direcciones.index('Barrio')]
                    direccion.party = tercero
                    direccion.party_name = tercero.name
                    direccion.street = dir[columna_direcciones.index('direccion')]
                    direccion.save()
            to_create.append(tercero)
        Party.save(to_create)
        
        return None


    @classmethod
    def carga_terceros(cls):
        terceros_tecno = []
        columnas_terceros = []
        direcciones_tecno = []
        columna_direcciones = []

        try:
            with conexion.cursor() as cursor:
                #Datos de terceros
                querycol = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TblTerceros' ORDER BY ORDINAL_POSITION")
                for d in querycol.fetchall():
                    columnas_terceros.append(d[0])
                query = cursor.execute("SELECT TOP(5) * FROM dbo.TblTerceros")
                terceros_tecno = list(query.fetchall())
                #Datos de direcciones
                querycol2 = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Terceros_Dir' ORDER BY ORDINAL_POSITION")
                for d in querycol2.fetchall():
                    columna_direcciones.append(d[0])
                query2 = cursor.execute("SELECT TOP(5) * FROM dbo.Terceros_Dir")
                direcciones_tecno = list(query2.fetchall())
                cursor.close()
                conexion.close()
        except Exception as e:
            print("ERROR consulta terceros: ", e)

        pool = Pool()
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Lang = pool.get('ir.lang')
        es, = Lang.search([('code', '=', 'es')])
        Mcontact = pool.get('party.contact_mechanism')
        to_create = []
        for ter in terceros_tecno:
            tercero = Party()
            tercero.create_date = ter[columnas_terceros.index('fecha_creacion')]
            tercero.code = ter[columnas_terceros.index('nit_cedula')]
            tercero.name = ter[columnas_terceros.index('nombre')]
            tercero.write_date = ter[columnas_terceros.index('Ultimo_Cambio_Registro')]
            if ter[columnas_terceros.index('Ultimo_Cambio_Registro')] == 'Natural':
                tercero.type_person = 'persona_natural'
            else:
                tercero.type_person = 'persona_juridica'
            tercero.lang = es
            for dir in direcciones_tecno:
                if dir[columna_direcciones.index('nit')] == ter[columnas_terceros.index('nit_cedula')]:
                    if dir[columna_direcciones.index('telefono_1')]:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir[columna_direcciones.index('telefono_1')]
                        contacto.party = tercero
                        contacto.save()
                    if dir[columna_direcciones.index('telefono_2')]:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir[columna_direcciones.index('telefono_2')]
                        contacto.party = tercero
                        contacto.save()
                    if ter[columnas_terceros.index('mail')]:
                        #Creacion e inserccion de metodos de contacto
                        contacto = Mcontact()
                        contacto.type = 'email'
                        contacto.value = ter[columnas_terceros.index('mail')]
                        contacto.party = tercero
                        contacto.save()
                    #Creacion e inserccion de direcciones
                    direccion = Address()
                    direccion.city = dir[columna_direcciones.index('ciudad')]
                    direccion.country = 50
                    direccion.name = dir[columna_direcciones.index('Barrio')]
                    direccion.party = tercero
                    direccion.party_name = tercero.name
                    direccion.street = dir[columna_direcciones.index('direccion')]
                    direccion.save()
            to_create.append(tercero)
        Party.save(to_create)
        return None


    @classmethod
    def carga_productos(cls):
        productos_tecno = []
        col_pro = []
        try:
            with conexion.cursor() as cursor:
                #Datos de productos
                querycol = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TblProducto' ORDER BY ORDINAL_POSITION")
                for d in querycol.fetchall():
                    col_pro.append(d[0])
                query = cursor.execute("SELECT TOP(100) * FROM dbo.TblProducto")
                productos_tecno = list(query.fetchall())
                cursor.close()
                conexion.close()
        except Exception as e:
            print("ERROR consulta 1: ", e)

        Producto = Pool().get('product.product')
        to_prod = []
        for p in productos_tecno:
            prod = Producto()
            prod.description = p[col_pro.index('Producto')]
            prod.template = p[col_pro.index('TipoProducto')]
            to_prod.append(prod)
        Producto.save(to_prod)


"""
    @classmethod
    @ModelView.btn_prueba
    def btn_prueba(cls, fecha = None):
        print("Prueba ")
        pass

"""