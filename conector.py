
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
        #cls.carga_terceros()
        cls.carga_productos()
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
                query = cursor.execute("SELECT TOP(50) * FROM dbo.TblTerceros")
                terceros_tecno = list(query.fetchall())
                #Datos de direcciones
                querycol2 = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Terceros_Dir' ORDER BY ORDINAL_POSITION")
                for d in querycol2.fetchall():
                    columna_direcciones.append(d[0])
                query2 = cursor.execute("SELECT TOP(50) * FROM dbo.Terceros_Dir")
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
            #Equivalencia tipo de identificacion
            if ter[columnas_terceros.index('tipo_identificacion')] == '1':
                tercero.type_document = '13'
            elif ter[columnas_terceros.index('tipo_identificacion')] == '2':
                tercero.type_document = '22'
            elif ter[columnas_terceros.index('tipo_identificacion')] == '3':
                tercero.type_document = '31'
            elif ter[columnas_terceros.index('tipo_identificacion')] == '4':
                tercero.type_document = '41'
            elif ter[columnas_terceros.index('tipo_identificacion')] == '6':
                tercero.type_document = '12'
            tercero.id_number = ter[columnas_terceros.index('nit_cedula')]
            #tercero.code = ter[columnas_terceros.index('nit_cedula')]
            tercero.name = ter[columnas_terceros.index('nombre')]
            tercero.first_name = ter[columnas_terceros.index('PrimerNombre')].strip()
            tercero.second_name = ter[columnas_terceros.index('SegundoNombre')].strip()
            tercero.first_family_name = ter[columnas_terceros.index('PrimerApellido')].strip()
            tercero.second_family_name = ter[columnas_terceros.index('SegundoApellido')].strip()
            tercero.write_date = ter[columnas_terceros.index('Ultimo_Cambio_Registro')]
            
            #Equivalencia tipo de persona y asignación True en declarante
            if ter[columnas_terceros.index('TipoPersona')].strip() == 'Natural':
                tercero.type_person = 'persona_natural'
            elif ter[columnas_terceros.index('TipoPersona')].strip() == 'Juridica':
                tercero.type_person = 'persona_juridica'
                tercero.declarante = True
            #Verificación e inserción codigo ciiu
            if ter[columnas_terceros.index('IdActividadEconomica')] != 0:
                tercero.ciiu_code = ter[columnas_terceros.index('IdActividadEconomica')]
            #Equivalencia regimen de impuestos
            idtipo_contribuyente = int(ter[columnas_terceros.index('IdTipoContribuyente')])
            if idtipo_contribuyente == 1 or idtipo_contribuyente == 4 or idtipo_contribuyente == 9:
                tercero.regime_tax = 'gran_contribuyente'
            elif idtipo_contribuyente == 2 or idtipo_contribuyente == 5 or idtipo_contribuyente == 6 or idtipo_contribuyente == 7 or idtipo_contribuyente == 8:
                tercero.regime_tax = 'regimen_responsable'
            elif idtipo_contribuyente == 3:
                tercero.regime_tax = 'regimen_no_responsable'
            tercero.lang = es
            cant_dir = 0
            for dir in direcciones_tecno:
                if dir[columna_direcciones.index('nit')] == ter[columnas_terceros.index('nit_cedula')]:
                    cant_dir += 1
                    if cant_dir == 1:
                        tercero.commercial_name = dir[columna_direcciones.index('NombreSucursal')]
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
                    if ter[columnas_terceros.index('mail')] != '0':
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


    @classmethod
    def carga_productos(cls):
        productos_tecno = []
        col_pro = []
        #col_gproducto = []
        #grupos_producto = []
        try:
            with conexion.cursor() as cursor:
                #Grupo de productos (categorias)
                #query_gproducto = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TblGrupoProducto' ORDER BY ORDINAL_POSITION")
                #for g in query_gproducto.fetchall():
                    #col_gproducto.append(g[0])
                #query_r_gproducto = cursor.execute("SELECT * FROM dbo.TblGrupoProducto")
                #grupos_producto = list(query_r_gproducto.fetchall())

                #Datos de productos
                querycol = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TblProducto' ORDER BY ORDINAL_POSITION")
                for d in querycol.fetchall():
                    col_pro.append(d[0])
                query = cursor.execute("SELECT TOP(100) * FROM dbo.TblProducto")
                productos_tecno = list(query.fetchall())
                cursor.close()
                conexion.close()
        except Exception as e:
            print("ERROR consulta producto: ", e)

        Producto = Pool().get('product.product')
        Template_Product = Pool().get('product.template')
        Category = Pool().get('product.category')
        ct, = Category.search([('id', '=', 1)])
        to_prod = []
        
        for p in productos_tecno:
            prod = Producto()
            temp = Template_Product()
            temp.name = p[col_pro.index('Producto')]
            #temp.customs_category = int(p[col_pro.index('IdGrupoProducto')])
            temp.default_uom = 1
            temp.type = 'goods'
            temp.list_price = int(p[col_pro.index('costo_unitario')])
            temp.categories = ct.id
            to_prod.append(prod)
        Producto.save(to_prod)
        


"""
    @classmethod
    @ModelView.btn_prueba
    def btn_prueba(cls, fecha = None):
        print("Prueba ")
        pass

"""