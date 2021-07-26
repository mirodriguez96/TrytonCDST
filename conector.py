
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
        cls.carga_terceros()
        #cls.carga_productos()
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
                query = cursor.execute("SELECT TOP(100) * FROM dbo.TblTerceros")
                terceros_tecno = list(query.fetchall())
                #Datos de direcciones
                querycol2 = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'Terceros_Dir' ORDER BY ORDINAL_POSITION")
                for d in querycol2.fetchall():
                    columna_direcciones.append(d[0])
                query2 = cursor.execute("SELECT * FROM dbo.Terceros_Dir")
                direcciones_tecno = list(query2.fetchall())
                cursor.close()
                conexion.close()
        except Exception as e:
            print("ERROR consulta terceros: ", e)
        
        pool = Pool()
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        Lang = pool.get('ir.lang')
        es, = Lang.search([('code', '=', 'es_419')])
        Mcontact = pool.get('party.contact_mechanism')
        to_create = []

        for ter in terceros_tecno:
            exists = cls.find_party(ter[columnas_terceros.index('nit_cedula')])
            if exists:
                exists.create_date = ter[columnas_terceros.index('fecha_creacion')]
                exists.type_document = cls.id_type(ter[columnas_terceros.index('tipo_identificacion')])
                exists.id_number = ter[columnas_terceros.index('nit_cedula')]
                exists.name = ter[columnas_terceros.index('nombre')].strip()
                exists.first_name = ter[columnas_terceros.index('PrimerNombre')].strip()
                exists.second_name = ter[columnas_terceros.index('SegundoNombre')].strip()
                exists.first_family_name = ter[columnas_terceros.index('PrimerApellido')].strip()
                exists.second_family_name = ter[columnas_terceros.index('SegundoApellido')].strip()
                exists.write_date = ter[columnas_terceros.index('Ultimo_Cambio_Registro')]
                exists.type_person = cls.person_type(ter[columnas_terceros.index('TipoPersona')].strip())
                if exists.type_person == 'persona_juridica':
                    exists.declarante = True
                #Verificación e inserción codigo ciiu
                if ter[columnas_terceros.index('IdActividadEconomica')] != 0:
                    exists.ciiu_code = ter[columnas_terceros.index('IdActividadEconomica')]
                exists.regime_tax = cls.tax_regime(int(ter[columnas_terceros.index('IdTipoContribuyente')]))
                exists.lang = es
                cant_dir = 0
                #Actualización de la dirección y metodos de contacto
                for dir in direcciones_tecno:
                    if dir[columna_direcciones.index('nit')] == ter[columnas_terceros.index('nit_cedula')]:
                        cant_dir += 1
                        if cant_dir == 1:
                            exists.commercial_name = dir[columna_direcciones.index('NombreSucursal')].strip()
                        contacts = cls.find_contact_mechanism(exists)
                        contador = 1
                        for contm in contacts:
                            campo = None
                            if contador == 1:
                                campo = 'telefono_1'
                            elif contador == 1:
                                campo = 'telefono_2'
                            else:
                                campo = 'mail'
                            contm.value = dir[columna_direcciones.index(campo)]
                            contm.save()
                            contador += 1
                        #Actualización de la dirección
                        direccion = cls.find_address(exists)
                        direccion.city = dir[columna_direcciones.index('ciudad')].strip()
                        direccion.name = dir[columna_direcciones.index('Barrio')].strip()
                        direccion.street = dir[columna_direcciones.index('direccion')].strip()
                        direccion.save()
                exists.save()
            else:
                tercero = Party()
                tercero.create_date = ter[columnas_terceros.index('fecha_creacion')]
                tercero.type_document = cls.id_type(ter[columnas_terceros.index('tipo_identificacion')])
                tercero.id_number = ter[columnas_terceros.index('nit_cedula')]
                #tercero.code = ter[columnas_terceros.index('nit_cedula')]
                tercero.name = ter[columnas_terceros.index('nombre')].strip()
                tercero.first_name = ter[columnas_terceros.index('PrimerNombre')].strip()
                tercero.second_name = ter[columnas_terceros.index('SegundoNombre')].strip()
                tercero.first_family_name = ter[columnas_terceros.index('PrimerApellido')].strip()
                tercero.second_family_name = ter[columnas_terceros.index('SegundoApellido')].strip()
                tercero.write_date = ter[columnas_terceros.index('Ultimo_Cambio_Registro')]

                #Equivalencia tipo de persona y asignación True en declarante
                tercero.type_person = cls.person_type(ter[columnas_terceros.index('TipoPersona')].strip())
                if tercero.type_person == 'persona_juridica':
                    tercero.declarante = True

                #Verificación e inserción codigo ciiu
                if ter[columnas_terceros.index('IdActividadEconomica')] != 0:
                    tercero.ciiu_code = ter[columnas_terceros.index('IdActividadEconomica')]
                #Equivalencia regimen de impuestos
                tercero.regime_tax = cls.tax_regime(int(ter[columnas_terceros.index('IdTipoContribuyente')]))
                tercero.lang = es
                cant_dir = 0
                for dir in direcciones_tecno:
                    if dir[columna_direcciones.index('nit')] == ter[columnas_terceros.index('nit_cedula')]:
                        cant_dir += 1
                        if cant_dir == 1:
                            tercero.commercial_name = dir[columna_direcciones.index('NombreSucursal')].strip()
                        #if dir[columna_direcciones.index('telefono_1')]:
                            #Creacion e inserccion de metodo de contacto 1
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir[columna_direcciones.index('telefono_1')]
                        contacto.party = tercero
                        contacto.save()
                        #if dir[columna_direcciones.index('telefono_2')]:
                            #Creacion e inserccion de metodo de contacto 2
                        contacto = Mcontact()
                        contacto.type = 'phone'
                        contacto.value = dir[columna_direcciones.index('telefono_2')]
                        contacto.party = tercero
                        contacto.save()
                        #if ter[columnas_terceros.index('mail')] != '0':
                            #Creacion e inserccion de metodo de contacto 3
                        contacto = Mcontact()
                        contacto.type = 'email'
                        contacto.value = ter[columnas_terceros.index('mail')]
                        contacto.party = tercero
                        contacto.save()
                        #Creacion e inserccion de direcciones
                        direccion = Address()
                        direccion.city = dir[columna_direcciones.index('ciudad')].strip()
                        direccion.country = 50
                        direccion.name = dir[columna_direcciones.index('Barrio')].strip()
                        direccion.party = tercero
                        direccion.party_name = tercero.name
                        direccion.street = dir[columna_direcciones.index('direccion')].strip()
                        direccion.save()
                to_create.append(tercero)
        Party.save(to_create)


    @classmethod
    def carga_productos(cls):
        productos_tecno = []
        col_pro = []
        col_gproducto = []
        grupos_producto = []
        try:
            #Con el with se cierra automaticamente el cursor
            with conexion.cursor() as cursor:
                #Grupo de productos (categorias)
                query_gproducto = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TblGrupoProducto' ORDER BY ORDINAL_POSITION")
                for g in query_gproducto.fetchall():
                    col_gproducto.append(g[0])
                query_r_gproducto = cursor.execute("SELECT * FROM dbo.TblGrupoProducto")
                grupos_producto = list(query_r_gproducto.fetchall())
                #print(grupos_producto)

                #Datos de productos
                querycol = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'TblProducto' ORDER BY ORDINAL_POSITION")
                for d in querycol.fetchall():
                    col_pro.append(d[0])
                query = cursor.execute("SELECT * FROM dbo.TblProducto")
                productos_tecno = list(query.fetchall())
        except Exception as e:
            print("ERROR consulta producto: ", e)

        Category = Pool().get('product.category')
        to_categorias = []
        for categoria in grupos_producto:
            existe = cls.buscar_categoria(str(categoria[col_gproducto.index('IdGrupoProducto')])+'-'+categoria[col_gproducto.index('GrupoProducto')])
            if not existe:
                categoria_prod = Category()
                categoria_prod.name = str(categoria[col_gproducto.index('IdGrupoProducto')])+'-'+categoria[col_gproducto.index('GrupoProducto')]
                to_categorias.append(categoria_prod)
        Category.save(to_categorias)

        Producto = Pool().get('product.product')
        Template_Product = Pool().get('product.template')
        to_producto = []
        for producto in productos_tecno:
            existe = cls.buscar_producto(producto[col_pro.index('IdProducto')])
            if existe:
                name_categoria = None
                for categoria in grupos_producto:
                    if categoria[col_gproducto.index('IdGrupoProducto')] == producto[col_pro.index('IdGrupoProducto')]:
                        name_categoria = str(categoria[col_gproducto.index('IdGrupoProducto')])+'-'+categoria[col_gproducto.index('GrupoProducto')]
                categoria_producto, = Category.search([('name', '=', name_categoria)])
                existe.template.name = producto[col_pro.index('Producto')].strip()
                existe.template.type = cls.tipo_producto(producto[col_pro.index('maneja_inventario')].strip())
                #equivalencia de unidad de medida
                if producto[col_pro.index('unidad_Inventario')] == 1:
                    existe.template.default_uom = 2
                else:
                    existe.template.default_uom = 1
                existe.template.list_price = int(producto[col_pro.index('costo_unitario')])
                existe.template.categories = [categoria_producto]
                existe.template.save()
            else:
                prod = Producto()
                name_categoria = None
                for categoria in grupos_producto:
                    if categoria[col_gproducto.index('IdGrupoProducto')] == producto[col_pro.index('IdGrupoProducto')]:
                        name_categoria = str(categoria[col_gproducto.index('IdGrupoProducto')])+'-'+categoria[col_gproducto.index('GrupoProducto')]
                categoria_producto, = Category.search([('name', '=', name_categoria)])
                temp = Template_Product()
                temp.code = producto[col_pro.index('IdProducto')]
                temp.name = producto[col_pro.index('Producto')].strip()
                temp.type = cls.tipo_producto(producto[col_pro.index('maneja_inventario')].strip())
                #equivalencia de unidad de medida
                if producto[col_pro.index('unidad_Inventario')] == 1:
                    temp.default_uom = 2
                else:
                    temp.default_uom = 1
                temp.list_price = int(producto[col_pro.index('costo_unitario')])
                temp.categories = [categoria_producto]
                prod.template = temp
                to_producto.append(prod)
        Producto.save(to_producto)
        

    @classmethod
    def buscar_categoria(cls, id_categoria):
        Category = Pool().get('product.category')
        try:
            categoria_producto, = Category.search([('name', '=', id_categoria)])
        except ValueError:
            return False
        else:
            return True

    @classmethod
    def buscar_producto(cls, id_producto):
        Product = Pool().get('product.product')
        try:
            producto, = Product.search([('code', '=', id_producto)])
        except ValueError:
            return False
        else:
            return producto

    @classmethod
    def tipo_producto(cls, inventario):
        #equivalencia del tipo de producto (si maneja inventario o no)
        if inventario == 'N':
            return 'service'
        else:
            return 'goods'

    @classmethod
    def find_party(cls, id):
        Party = Pool().get('party.party')
        try:
            party, = Party.search([('id_number', '=', id)])
        except ValueError:
            return False
        else:
            return party


    @classmethod
    def id_type(cls, type):
        #Equivalencia tipo de identificacion
        if type == '1':
            return '13'
        elif type == '2':
            return '22'
        elif type == '3':
            return '31'
        elif type == '4':
            return '41'
        elif type == '6':
            return '12'
        else:
            return None


    @classmethod
    def person_type(cls, type):
        #Equivalencia tipo de persona y asignación True en declarante
        if type == 'Natural':
            return 'persona_natural'
        elif type == 'Juridica':
            return 'persona_juridica'

    @classmethod
    def tax_regime(cls, regime):
        #Equivalencia regimen de impuestos
        if regime == 1 or regime == 4:
            return 'gran_contribuyente'
        elif regime == 2 or regime == 5 or regime == 6 or regime == 7 or regime == 8:
            return 'regimen_responsable'
        elif regime == 3:
            return'regimen_no_responsable'
        else:
            return None


    @classmethod
    def find_address(cls, party):
        Address = Pool().get('party.address')
        try:
            address, = Address.search([('party', '=', party)])
        except ValueError:
            return False
        else:
            return address


    @classmethod
    def find_contact_mechanism(cls, party):
        Contact = Pool().get('party.contact_mechanism')
        try:
            contact, = Contact.search([('party', '=', party)])
        except ValueError:
            return False
        else:
            return contact