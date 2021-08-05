#from trytond.model import ModelView
from trytond.wizard import Wizard, StateTransition#, StateView, StateAction, Button
import datetime
from trytond.pool import Pool
from trytond.transaction import Transaction
#from trytond.pyson import PYSONEncoder
from trytond.exceptions import UserError
from conexion import conexion


__all__ = [
    'ActualizarVentas',
    'CargarVentas',
    ]

#Nota: el uso principal de los asistentes suele ser realizar acciones basadas en alguna entrada del usuario.

class ActualizarVentas(Wizard):
    'ActualizarVentas'
    __name__ = 'conector.terceros.actualizar_ventas'
    start_state = 'actualizar_venta'
    actualizar_venta = StateTransition()

    def transition_actualizar_venta(self):
        if Transaction().context.get('active_model', '') != 'conector.terceros':
            raise UserError("Error", "Debe estar en el modelo de actualizacion")
        pool = Pool()
        Product = pool.get('product.product')
        Sale = pool.get('sale.sale')
        Line = pool.get('sale.line')
        Party = pool.get('party.party')
        Address = pool.get('party.address')
        documentos = self.get_data_db_tecno('Documentos')
        coluns_doc = self.get_columns_db_tecno('Documentos')
        create_sale = []
        for vent in documentos:
            numero_doc = vent[coluns_doc.index('Numero_documento')]
            venta = Sale()
            line = Line()
            #venta.company = 3
            #venta.currency = 1
            venta.description = vent[coluns_doc.index('notas')]
            venta.invoice_method = 'manual'
            venta.invoice_state = 'none'
            venta.invoice_type = 'M'
            fecha = str(vent[coluns_doc.index('Fecha_Orden_Venta')]).split()[0]
            fecha_date = datetime.date(int(fecha[0]), int(fecha[1]), int(fecha[2]))
            venta.sale_date = fecha_date
            venta.shipment_method = 'manual'
            venta.shipment_state = 'none'
            venta.state = 'done'
            party = Party.search([('id_number', '=', vent[coluns_doc.index('nit_Cedula')])])
            venta.party = party.id
            address = Address.search([('party', '=', party.id)], limit=1)
            venta.invoice_address = address[0].id
            venta.shipment_address = address[0].id

            documentos_linea = self.get_line_where(str(numero_doc))
            col_line = self.get_columns_db_tecno('Documentos_Lin')
            create_line = []
            for lin in documentos_linea:
                #Procedemos a realizar una venta
                producto = Product.search([('code', '=', lin[col_line.index('IdProducto')])])
                line.product = producto.id
                line.quantity = int(lin[col_line.index('Cantidad_Facturada')])
                line.sale = venta
                line.type = 'line'
                line.unit = 1
                create_line.append(line)
            create_sale.append(venta)
        Line.save(create_line)
        Sale.save(create_sale)
        return 'end'


    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_data_db_tecno(cls, table):
        data = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT TOP (100) * FROM dbo."+table)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return data
    
    #Esta función se encarga de traer todos los datos de una tabla dada de la bd TecnoCarnes
    @classmethod
    def get_line_where(cls, id):
        data = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT TOP (100) * FROM dbo.Documentos_Lin WHERE Numero_Documento = "+id)
                data = list(query.fetchall())
        except Exception as e:
            print("ERROR QUERY Documentos_Lin: ", e)
        return data

    #Función encargada de consultar las columnas pertenecientes a 'x' tabla de la bd de TecnoCarnes
    @classmethod
    def get_columns_db_tecno(cls, table):
        columns = []
        try:
            with conexion.cursor() as cursor:
                query = cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '"+table+"' ORDER BY ORDINAL_POSITION")
                for q in query.fetchall():
                    columns.append(q[0])
        except Exception as e:
            print("ERROR QUERY "+table+": ", e)
        return columns



"""
class ActualizarVentas(Wizard):
    'ActualizarVentas'

    #Los asistentes __name__ normalmente deben estar compuestos
    #por el modelo en el que trabajará el asistente (conector.terceros), 
    #luego la acción que se realizará (actualizar_ventas). 
    #La acción suele ser un verbo.

    __name__ = 'conector.terceros.actualizar_ventas'

    #Estado inicial que le pedira al usuario una entrada
    start_state = 'parameters'
    #vista donde se ingresa la entrada, que activa el siguiente estado
    parameters = StateView('conector.terceros.cargar_ventas.parameters',
        'conector.cargar_ventas_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Create', 'actualizar_venta', 'tryton-go-next', default=True)])
    #Estado transitorio activado por la entrada del usuario
    actualizar_venta = StateTransition()
    #open_exemp = StateAction('conector.actualizar_venta')


    def default_parameters(self, name):
        #El context es un diccionario que contiene datos sobre el contexto (...) en el que se está ejecutando el código actual.

        #active_model: es el modelo que se muestra actualmente al usuario. En nuestro caso,conector.terceros
        #active_ids: es la lista de los ID de los registros que se seleccionaron cuando se desencadenó la acción
        #active_id: es el primero de esos registros (o el único si solo se seleccionó un registro).
        
        if Transaction().context.get('active_model', '') != 'conector.terceros':
            #generamos un mensaje de error
            #self.raise_user_error('invalid_model')
            raise UserError("You cannot process.", "because…")
        return {
            #'date': datetime.date.today(),
            #'id': Transaction().context.get('active_id'),
            }

    def do_open_exemplaries(self, action):
        #Aquí configuramos la clave pyson_domain para forzar un dominio / restricción en la pestaña,
        #lo que hará que muestre solo los identificadores que coinciden con los elementos que acabamos de crear.
        action['pyson_domain'] = PYSONEncoder().encode([
                ('id', 'in', [x.id for x in self.parameters.exemplaries])])
        return action, {}


class CargarVentas(ModelView):
    'CargarVentas'
    __name__ = 'conector.terceros.cargar_ventas.parameters'

    def transition_actualizar_venta(self):
        if (not self.parameters):
            print('Error')
            raise UserError("You cannot process.", "because…")
            #self.raise_user_error('invalid_date')
        #Si no...
        Exemplary = Pool().get('library.book.exemplary')
        to_create = []
        while len(to_create) < self.parameters.number_of_exemplaries:
            exemplary = Exemplary()
            exemplary.book = self.parameters.book
            exemplary.acquisition_date = self.parameters.acquisition_date
            exemplary.acquisition_price = self.parameters.acquisition_price
            exemplary.identifier = self.parameters.identifier_start + str(
                len(to_create) + 1)
            to_create.append(exemplary)
        Exemplary.save(to_create)
        self.parameters.exemplaries = to_create
        return 'open_exemplaries'
"""


