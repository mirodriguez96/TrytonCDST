from collections import OrderedDict
from datetime import date
from decimal import Decimal

from sql import Table
from sql.aggregate import Sum
from sql.operators import Between, Like
from trytond.exceptions import UserError
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, If
from trytond.report import Report
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard

STATES = [("", ""), ("draft", "Borrador"), ("done", "Finalizado")]
TYPE_DOCUMENT = [("", "")]


class Sale(metaclass=PoolMeta):
    'Sale inheritance Model'
    __name__ = 'sale.sale'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False, select=True)
    invoice_amount_tecno = fields.Numeric('Value_Tecno',
                                          digits=(16, 2),
                                          required=False)
    tax_amount_tecno = fields.Numeric('Value_Tax_Tecno',
                                      digits=(16, 2),
                                      required=False)

    @classmethod
    def import_data_sale(cls):
        print('RUN VENTAS')
        cls.import_sales_tecnocarnes('1')

    @classmethod
    def import_data_sale_return(cls):
        print('RUN DEVOLUCIONES DE VENTAS')
        cls.import_sales_tecnocarnes('2')

    @classmethod
    def import_sales_tecnocarnes(cls, swt):
        """Function to import sales from tecno
        and create it in Tryton

        Args:
            swt (String): Switch in tecnocarnes
        """

        pool = Pool()
        Config = pool.get('conector.configuration')
        Module = pool.get('ir.module')
        Sale = pool.get('sale.sale')
        User = pool.get('res.user')

        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update('VENTAS')
        actualizacion_che = Actualizacion.create_or_update('SIN DOCUMENTO CHE')

        sale_in_exception = []
        venta_pos = []

        print('Obteniendo info')
        data = Config.get_documentos_tecno(swt)
        configuration = Config.get_configuration()
        company_operation = Module.search([('name', '=', 'company_operation'),
                                           ('state', '=', 'activated')])

        if not configuration or not data:
            print('No se obtuvo info')
            return

        if not company_operation:
            print('Modulo centro de operacion inactivo')
            log = {"ERROR": """Modulo centro de operaciones inactivo"""}
            cls.update_logs_from_imports(
                actualizacion, actualizacion_che, logs_che=log)
            return

        print('Obteniendo el tipo de venta')
        pdevoluciones_pos = Config.get_data_parametros('10')
        if pdevoluciones_pos:
            pdevoluciones_pos = (pdevoluciones_pos[0].Valor).strip().split(',')
            venta_pos += pdevoluciones_pos
        pventa_pos = Config.get_data_parametros('8')
        if pventa_pos:
            pventa_pos = (pventa_pos[0].Valor).strip().split(',')
            venta_pos += pventa_pos
        venta_electronica = Config.get_data_parametros('9')
        if venta_electronica:
            venta_electronica = (venta_electronica[0].Valor).strip().split(',')

        # Build the SALE
        print('Recorriendo las ventas')
        for venta in data:
            try:
                numero_doc = venta.Numero_documento
                tipo_doc = venta.tipo
                sw = venta.sw
                id_venta = cls.build_id_tecno(
                    sw=sw, type_doc=tipo_doc, number_doc=numero_doc)
                print(f'Venta {id_venta}')
                # build date_sale from tecnocarnes
                date_ = str(venta.fecha_hora).split()[0].split('-')
                date_tecno = date(int(date_[0]), int(date_[1]),
                                  int(date_[2]))

                (shop, party, bodega,
                 plazo_pago, sale_device,
                 documentos_linea, analytic_account,
                 operation_center, exception_) = cls.validate_sale_from_tecno(actualizacion, actualizacion_che,
                                                                              data=data, venta=venta
                                                                              )
                if exception_:
                    continue

                sale = cls.build_sale_from_tecno_data(actualizacion, actualizacion_che,
                                                      venta=venta, shop=shop,
                                                      fecha_date=date_tecno, party=party,
                                                      bodega=bodega, plazo_pago=plazo_pago,
                                                      venta_electronica=venta_electronica,
                                                      venta_pos=venta_pos, sale_device=sale_device,
                                                      documentos_linea=documentos_linea,
                                                      analytic_account=analytic_account,
                                                      operation_center=operation_center,
                                                      sale_in_exception=sale_in_exception
                                                      )
                if sale:
                    if id_venta in sale_in_exception:
                        continue
                    Sale.quote([sale])
                    Sale.confirm([sale])
                    Sale.process([sale])
                    cls.finish_shipment_process(sale, numero_doc, Config,
                                                tipo_doc)
                    cls._post_invoices(
                        actualizacion, actualizacion_che, sale, venta)

                    pagos = Config.get_tipos_pago(id_venta)
                    if pagos:
                        args_statement = {
                            'device': sale_device,
                            'usuario': venta.usuario,
                        }
                        cls.set_payment_pos(
                            actualizacion, actualizacion_che,
                            pagos, sale, args_statement)

                        Sale.update_state([sale])
                    elif sale.payment_term.id_tecno == '0':
                        log = {
                            id_venta: """No se encontraron pagos
                            asociados en tecnocarnes (documentos_che)"""}
                        cls.update_logs_from_imports(
                            actualizacion, actualizacion_che, logs_che=log)
                        cls.delete_imported_sales([sale], cod='E')
                        continue
                    success = cls.update_exportado_tecno(
                        id_tecno=id_venta, exportado="T")
                    if not success:
                        break
                    Sale.process([sale])
                    Transaction().commit()
                    print('Venta guardada')
            except Exception as error:
                Transaction().rollback()
                if id_venta in sale_in_exception and sale:
                    cls.delete_tryton_sale(sale)
                success = cls.update_exportado_tecno(
                    id_tecno=id_venta, exportado="E")
                if not success:
                    break
                log = {id_venta: f"""EXCEPCION: {str(error)}"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs_che=log)
        print('FINISH VENTAS')

    @classmethod
    def validate_sale_from_tecno(cls, actualizacion, actualizacion_che,
                                 data=None, venta=None,
                                 ):
        """Function to validate sale info from tecno and
        return necesary data to build sale in tecno if
        validation its ok.

        Args:
            actualizacion (model): actualizacion model in tryton
            actualizacion_che (model): actualizacion model in tryton
            data (JSON, optional): Data from tecno. Defaults to None.
            venta (JSON, optional): Sale from tecno. Defaults to None.

        Returns:
            data: data necesary to create sale in Tryton
        """

        pool = Pool()
        CompanyOperation = pool.get('company.operation_center')
        AnalyticAccount = pool.get('analytic_account.account')
        payment_term = pool.get('account.invoice.payment_term')
        Config = pool.get('conector.configuration')
        Location = pool.get('stock.location')
        SaleDevice = pool.get('sale.device')
        Period = pool.get('account.period')
        SaleLine = pool.get('sale.line')
        Party = pool.get('party.party')
        Shop = pool.get('sale.shop')
        Sale = pool.get('sale.sale')
        shop = party = bodega = plazo_pago = sale_device = documentos_linea = analytic_account = operation_center = None
        exception = False

        numero_doc = venta.Numero_documento
        tipo_doc = venta.tipo
        sw = venta.sw
        id_venta = cls.build_id_tecno(
            sw=sw, type_doc=tipo_doc, number_doc=numero_doc)
        date_ = str(venta.fecha_hora).split()[0].split('-')
        parties = Party._get_party_documentos(data, 'nit_Cedula')
        operation_center = CompanyOperation.search([],
                                                   order=[('id', 'DESC')],
                                                   limit=1)
        print('llega')
        while True:
            log = {}
            # Validate that operation center exist
            if not operation_center:
                print(f'Falta centro de operación - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: """Falta centro de operación"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break

            # Validate already sale created in Tryton
            already_sale = Sale.search([('id_tecno', '=', id_venta)])
            if already_sale:
                print(f'Venta existente - {id_venta}')
                sale_tecno_validate = cls.validate_already_sale_from_tecno(
                    actualizacion, actualizacion_che, already_sale, venta, id_venta)
                if sale_tecno_validate:
                    exception = True
                    break

            if venta.anulado == 'S':
                print(f'Venta anulada en tecno - ({id_venta})')
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="X")
                log = {
                    id_venta: """Documento anulado en TecnoCarnes"""
                }
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                exception = True
                break

            if venta.sw == 2:
                print(f'Validando devolucion - ({id_venta})')
                dcto_base = str(venta.Tipo_Docto_Base) + '-' + str(
                    venta.Numero_Docto_Base)
                original_invoice = Sale.search([('number', '=', dcto_base)
                                                ])
                if not original_invoice:
                    print(f'No se encontro devolucion - ({id_venta})')
                    cls.update_exportado_tecno(
                        id_tecno=id_venta, exportado="E")
                    log = {
                        id_venta: f"""La devolucion {id_venta}
                        no encuentra la referencia {dcto_base}
                        para ser cruzado"""
                    }
                    cls.update_logs_from_imports(
                        actualizacion, actualizacion_che, logs=log)
                    exception = True
                    break

            name_period = f"{date_[0]}-{date_[1]}"
            period_ = Period.search([('name', '=', name_period)])
            if period_[0].state == 'close':
                print(f'Periodo cerrrado - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: """El periodo del documento se encuentra cerrado,
                        no es posible la creacion"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break

            if hasattr(SaleLine, 'analytic_accounts'):
                tbltipodocto = Config.get_tbltipodoctos(tipo_doc)
                if tbltipodocto and tbltipodocto[0].Encabezado != '0':
                    analytic_account = AnalyticAccount.search([
                        ('code', '=', str(tbltipodocto[0].Encabezado))
                    ])
                    if not analytic_account:
                        print(f'Sin analitica - ({id_venta})')
                        exception = True
                        cls.update_exportado_tecno(
                            id_tecno=id_venta, exportado="E")
                        log = {id_venta: f"""No se encontrola asignacion
                                de la cuenta analitica en TecnoCarnes
                                {str(tbltipodocto[0].Encabezado)}"""}
                        cls.update_logs_from_imports(
                            actualizacion, actualizacion_che, logs=log)
                        break
                    analytic_account = analytic_account[0]

            nit_cedula = venta.nit_Cedula.replace('\n', "")
            if nit_cedula in parties['active']:
                party = parties['active'][nit_cedula]
            if not party:
                if nit_cedula not in parties['inactive']:
                    print(f'Sin tercero - ({id_venta})')
                    exception = True
                    cls.update_exportado_tecno(
                        id_tecno=id_venta, exportado="E")
                    log = {id_venta: f"""No se encontro el tercero {nit_cedula}"""}
                    cls.update_logs_from_imports(
                        actualizacion, actualizacion_che, logs=log)
                    break

            # asgined the location
            id_tecno_bodega = venta.bodega
            bodega = Location.search([('id_tecno', '=', id_tecno_bodega)])
            if not bodega:
                print(f'Sin Bodega - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: f"""Bodega {id_tecno_bodega} no existe"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break
            bodega = bodega[0]

            # asigned the warehouse
            shop = Shop.search([('warehouse', '=', bodega.id)])
            if not shop:
                print(f'Bodega no existe - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {
                    id_venta: f"""Tienda (bodega) {id_tecno_bodega} no existe"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break
            shop = shop[0]

            # asigned payment condition
            condicion = venta.condicion
            plazo_pago = payment_term.search([('id_tecno', '=', condicion)
                                              ])
            if not plazo_pago:
                print(f'Plazo de pago no existe - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: f"""Plazo de pago {condicion} no existe"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break
            plazo_pago = plazo_pago[0]

            # get product lines for sale
            documentos_linea = Config.get_lineasd_tecno(id_venta)
            if not documentos_linea:
                print(f'No se encontraron líneas para la venta - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: """No se encontraron líneas para la venta"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break

            # asigned sale (terminal)
            id_tecno_device = venta.pc + '-' + str(venta.bodega)
            sale_device = SaleDevice.search([
                'OR', ('id_tecno', '=', id_tecno_device),
                [
                    'AND', ('id_tecno', '=', venta.pc),
                    ('shop.warehouse.id_tecno', '=', venta.bodega)
                ]
            ])
            if not sale_device:
                print(f'Terminal de venta no existe - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: f"""Terminal de venta {id_tecno_device} no existe"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break

            elif len(sale_device) > 1:
                print(f'Terminal repetida - ({id_venta})')
                exception = True
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: """Hay mas de una terminal que concuerdan
                        con el mismo equipo de venta y bodega"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                break
            sale_device = sale_device[0]
            break

        return (shop, party, bodega, plazo_pago, sale_device,
                documentos_linea, analytic_account,
                operation_center, exception
                )

    @classmethod
    def build_sale_from_tecno_data(
            cls, actualizacion, actualizacion_che,
            venta=None, shop=None,
            fecha_date=None, party=None,
            bodega=None, plazo_pago=None,
            venta_electronica=None, venta_pos=None,
            sale_device=None, documentos_linea=None,
            analytic_account=None, operation_center=None,
            sale_in_exception=[]
    ):

        pool = Pool()
        AnalyticAccount = pool.get('analytic_account.account')
        Product = pool.get('product.product')
        Address = pool.get('party.address')
        SaleLine = pool.get('sale.line')
        Tax = pool.get('account.tax')
        Sale = pool.get('sale.sale')
        User = pool.get('res.user')
        sale_in_exception = []
        retencion_iva = False
        retencion_ica = False
        retencion_rete = False
        sw = venta.sw
        numero_doc = venta.Numero_documento
        tipo_doc = venta.tipo

        id_venta = cls.build_id_tecno(
            sw=sw, type_doc=tipo_doc, number_doc=numero_doc)
        value_total = Decimal(str(round(venta.valor_total,
                                        2)))
        caused_retention = Decimal(str(round(venta.retencion_causada,
                                             2)))
        invoice_amount_tecno = value_total - caused_retention
        if venta.Valor_impuesto:
            tax_amount_tecno = Decimal(
                str(round(venta.Impuesto_Consumo, 2)))
        else:
            tax_amount_tecno = Decimal(0)

        # with Transaction().set_user(1):
        #     User.shop = shop
        #     context = User.get_preferences()
        # sale = Sale()
        # with Transaction().set_context(context,
        #                                shop=shop.id,
        #                                _skip_warnings=True):

        sale = Sale()
        sale.number = tipo_doc + '-' + str(numero_doc)
        sale.reference = tipo_doc + '-' + str(numero_doc)
        sale.id_tecno = id_venta
        sale.description = (venta.notas).replace('\n', ' ').replace(
            '\r', '').replace('\t', ' ')
        sale.invoice_type = 'C'
        sale.sale_date = fecha_date
        sale.party = party.id
        sale.invoice_party = party.id
        sale.shipment_party = party.id
        sale.warehouse = bodega
        sale.payment_term = plazo_pago
        sale.self_pick_up = False
        sale.invoice_number = sale.number
        sale.invoice_date = fecha_date
        sale.invoice_amount_tecno = Decimal(
            str(round(invoice_amount_tecno, 2)))
        sale.tax_amount_tecno = Decimal(str(round(tax_amount_tecno,
                                                  2)))
        """ Se revisa si la venta es clasificada como electronica o
                pos y se cambia el tipo"""
        if tipo_doc in venta_electronica:
            sale.invoice_type = '1'
        elif tipo_doc in venta_pos:
            sale.shop = shop
            sale.invoice_type = 'P'
            sale.pos_create_date = fecha_date
            sale.sale_device = sale_device
        """ Se busca una dirección del tercero para agregar en la
                factura y envio"""
        address = Address.search([('party', '=', party.id)], limit=1)
        if address:
            sale.invoice_address = address[0].id
            sale.shipment_address = address[0].id
        sale.save()

        """Se revisa si se aplico alguno de
                los 3 impuestos en la venta"""
        if venta.retencion_iva > 0:
            retencion_iva = True

        if venta.retencion_ica > 0:
            retencion_ica = True

        if venta.retencion_causada > 0:
            if not retencion_iva and not retencion_ica:
                retencion_rete = True
            elif (venta.retencion_iva
                    + venta.retencion_ica) != venta.retencion_causada:
                retencion_rete = True
        print('Recorriendo lineas de venta')
        for lin in documentos_linea:
            impuestos_linea = []
            producto = Product.search([
                'OR', ('id_tecno', '=', str(lin.IdProducto)),
                ('code', '=', str(lin.IdProducto))
            ])

            if not producto:
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: f"""No se encontro el producto {str(lin.IdProducto)}-
                            Revisar si tiene variante o esta inactivo"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                sale_in_exception.append(id_venta)
                break

            if len(producto) > 1:
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: """Hay mas de un producto que tienen
                            el mismo código o id_tecno"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                sale_in_exception.append(id_venta)
                break

            producto, = producto
            """Validate if product is not salable"""
            if not producto.template.salable:
                cls.update_exportado_tecno(id_tecno=id_venta, exportado="E")
                log = {id_venta: f"""El producto {str(lin.IdProducto)}
                            no esta marcado como vendible"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                sale_in_exception.append(id_venta)
                break
            cantidad_facturada = round(float(lin.Cantidad_Facturada),
                                       3)

            if producto.template.default_uom.id == 1:
                cantidad_facturada = int(cantidad_facturada)
            if cantidad_facturada < 0:  # negativo = devolucion (Tecno)
                cant = cantidad_facturada
                for line in sale.lines:
                    line_quantity = line.quantity
                    if sw == 2:
                        line_quantity = (line_quantity * -1)
                        cant = (cantidad_facturada * -1)
                    if line.product == producto and line_quantity > 0:
                        total_quantity = round((line.quantity + cant),
                                               3)
                        line.quantity = total_quantity
                        line.save()
                        break
                continue

            linea = SaleLine()
            linea.sale = sale
            linea.product = producto
            linea.type = 'line'
            linea.unit = producto.sale_uom

            # Validate if is sale return
            if sw == 2:
                linea.quantity = cantidad_facturada * -1
                dcto_base = str(venta.Tipo_Docto_Base) + '-' + str(
                    venta.Numero_Docto_Base)

                # asigned document reference
                sale.reference = dcto_base
                sale.comment = f"DEVOLUCIÓN DE LA FACTURA {dcto_base}"
            else:
                linea.quantity = cantidad_facturada

            linea.operation_center = operation_center[0]

            # validate changes and get taxes from product
            linea.on_change_product()

            # validate if tax consumption was appyl
            impuesto_consumo = lin.Impuesto_Consumo

            # validate withholdings and tax consumption
            for impuestol in linea.taxes:
                clase_impuesto = impuestol.classification_tax_tecno
                if clase_impuesto == '05' and retencion_iva:
                    if impuestol not in impuestos_linea:
                        impuestos_linea.append(impuestol)
                elif clase_impuesto == '06' and retencion_rete:
                    if impuestol not in impuestos_linea:
                        impuestos_linea.append(impuestol)
                elif clase_impuesto == '07' and retencion_ica:
                    if impuestol not in impuestos_linea:
                        impuestos_linea.append(impuestol)
                elif impuestol.consumo and impuesto_consumo > 0:
                    # validate tax consumption for apply
                    tax = Tax.search([('consumo', '=', True),
                                      ('type', '=', 'fixed'),
                                      ('amount', '=',
                                     impuesto_consumo),
                                      [
                        'OR',
                        ('group.kind', '=', 'sale'),
                        ('group.kind', '=', 'both')
                    ]])
                    if tax:
                        if len(tax) > 1:
                            cls.update_exportado_tecno(
                                id_tecno=id_venta, exportado="E")
                            log = {id_venta: f"""Se encontro mas de un impuesto de tipo consumo
                                        con el importe igual a {impuesto_consumo} del grupo venta,
                                        recuerde que se debe manejar un unico impuesto con esta configuracion"""}
                            cls.update_logs_from_imports(
                                actualizacion, actualizacion_che, logs=log)
                            sale_in_exception.append(id_venta)
                            break
                        tax, = tax
                        impuestos_linea.append(tax)
                    else:
                        cls.update_exportado_tecno(
                            id_tecno=id_venta, exportado="E")
                        log = {id_venta: f"""No se encontró el impuesto al consumo con el
                                    importe igual a {impuesto_consumo}"""}
                        cls.update_logs_from_imports(
                            actualizacion, actualizacion_che, logs=log)
                        sale_in_exception.append(id_venta)
                        break

                elif (clase_impuesto != '05'
                        and clase_impuesto != '06'
                        and clase_impuesto != '07'
                        and not impuestol.consumo):
                    if impuestol not in impuestos_linea:
                        impuestos_linea.append(impuestol)

            linea.taxes = impuestos_linea
            linea.base_price = lin.Valor_Unitario
            linea.unit_price = lin.Valor_Unitario

            # validate if product line have a discount to add it
            if lin.Porcentaje_Descuento_1 > 0:
                porcentaje = lin.Porcentaje_Descuento_1 / 100
                linea.base_price = lin.Valor_Unitario
                linea.discount_rate = Decimal(str(porcentaje))
                linea.on_change_discount_rate()

            # save the line for the SALE
            if analytic_account:
                AnalyticEntry = pool.get('analytic.account.entry')
                root, = AnalyticAccount.search([('type', '=', 'root')])
                analytic_entry = AnalyticEntry()
                analytic_entry.root = root
                analytic_entry.account = analytic_account
                linea.analytic_accounts = [analytic_entry]
            linea.save()
            print(f'Guardando linea {linea}')

        if id_venta in sale_in_exception:
            print('Eliminando venta con excepcion')
            cls.delete_tryton_sale(sale)
            Transaction().commit()
            return None
        Transaction().commit()
        return sale

    @classmethod
    def delete_tryton_sale(cls, sale):
        """Function that deletes a sale in tryton
        that had an error in the import

        Args:
            sale (model): sale model
        """
        pool = Pool()
        Sale = pool.get('sale.sale')

        sale.number = None
        sale.invoice_number = None
        sale.state = "draft"
        sale.save()
        Sale.delete([sale])
        print('Eliminando venta con excepcion')

    @classmethod
    def build_id_tecno(cls, sw=None, type_doc=None, number_doc=None):
        id_tecno = str(sw) + '-' + type_doc + '-' + str(number_doc)
        return id_tecno

    @classmethod
    def update_exportado_tecno(cls, id_tecno, exportado):
        """Function to update exportado column in Tecno Database

        Args:
            id_tecno (String): data from tryton
            exportado (String): Value to udate ('E','X','N')
        """
        pool = Pool()
        Config = pool.get('conector.configuration')
        success = Config.update_exportado(id_tecno, exportado)
        return success

    @classmethod
    def update_logs_from_imports(cls, actualizacion, actualizacion_che, logs=None, logs_che=None):
        """Function to create logs

        Args:
            logs (dict): Contain id_tecno key and log message. Defaults to None.
            logs_che (dict): Contain id_tecno key and log message. Defaults to None.
        """

        if logs:
            actualizacion.add_logs(logs)
        if logs_che:
            actualizacion_che.add_logs(logs_che)

    @classmethod
    def validate_already_sale_from_tecno(cls, actualizacion, actualizacion_che, sale_tryton, sale_tecno, id_sale_tecno):
        """
        Function to validate already sale from tecno.
            Validate if sale was deleted in tecno and
            if period in tryton isn't close and deleted

        Args:
            sale_tryton (sale_sale): sale in tryton
            sale_tecno (JSON): sale from tecno
            id_sale_tecno (string): id_tecno in tryton

        Returns:
            boolean: True
        """

        pool = Pool()
        Period = pool.get('account.period')
        if sale_tecno.anulado == 'S':
            dat = str(sale_tecno.fecha_hora).split()[0].split('-')
            name = f"{dat[0]}-{dat[1]}"
            validate_period = Period.search([('name', '=', name)])
            # Validate if period close and continue
            if validate_period[0].state == 'close':
                print('Periodo cerrado')
                cls.update_exportado_tecno(id_sale_tecno, exportado="E")
                log = {
                    id_sale_tecno: """EXCEPCION: EL PERIODO DEL
                    DOCUMENTO SE ENCUENTRA CERRADO Y NO ES
                    POSIBLE SU ELIMINACION O MODIFICACION
                    """
                }
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                return True

            # Delete sale from tryton if was deleted from tecno
            print('Eliminando venta que fue anulada ({id_sale_tecno})')
            cls.delete_imported_sales(sale_tryton, cod="X")
            log = {id_sale_tecno: """El documento fue eliminado de tryton
                            porque fue anulado en TecnoCarnes"""
                   }
            cls.update_logs_from_imports(
                actualizacion, actualizacion_che, logs=log)
            return True

        print('Venta sera marcada en T')
        cls.update_exportado_tecno(id_sale_tecno, exportado="T")
        return True

    @ classmethod
    def finish_shipment_process(cls, sale, numero_doc, Config, tipo_doc):
        """
        Function to end the process sale sending
        """
        pool = Pool()
        Product = pool.get('product.product')

        dictprodut = {}
        select = f"SELECT tr.IdProducto, tr.IdResponsable\
                FROM TblProducto tr \
                join Documentos_Lin dl  \
                on tr.IdProducto = dl.IdProducto \
                WHERE dl.Numero_Documento = {numero_doc} and dl.tipo = {tipo_doc};"

        result = Config.get_data(select)

        for item in result:
            dictprodut[item[0]] = {
                'idresponsable': str(item[1]),
            }

        for shipment in sale.shipments:
            shipment.reference = sale.number
            shipment.effective_date = sale.sale_date
            shipment.save()
            for productmove in shipment.outgoing_moves:
                idTecno = int(productmove.product.id_tecno)
                if idTecno in dictprodut.keys():
                    id_ = dictprodut[idTecno]['idresponsable']
                    producto = Product.search(
                        ['OR', ('id_tecno', '=', id_), ('code', '=', id_)])
                    if producto:
                        product, = producto
                        if productmove.product.default_uom.symbol == product.default_uom.symbol:
                            productmove.product = product

                    productmove.save()
            shipment.wait([shipment])
            shipment.pick([shipment])
            shipment.pack([shipment])
            shipment.done([shipment])

        for shipment in sale.shipment_returns:
            shipment.reference = sale.number
            shipment.effective_date = sale.sale_date
            for productmove in shipment.incoming_moves:
                idTecno = int(productmove.product.id_tecno)
                if idTecno in dictprodut.keys():
                    id_ = dictprodut[idTecno]['idresponsable']
                    producto = Product.search(
                        ['OR', ('id_tecno', '=', id_), ('code', '=', id_)])
                    if producto:
                        product, = producto
                        if productmove.product.default_uom.symbol == product.default_uom.symbol:
                            productmove.product = product

                    productmove.save()
            shipment.save()
            shipment.receive([shipment])
            shipment.done([shipment])

    @ classmethod
    def _post_invoices(cls, actualizacion, actualizacion_che, sale, venta):
        """Function to update invoices and sends with sale info"""

        pool = Pool()
        Invoice = pool.get('account.invoice')
        PaymentLine = pool.get('account.invoice-account.move.line')
        Config = pool.get('conector.configuration')

        # process sale to build invoice
        if not sale.invoices:
            id_tecno_ = sale.id_tecno
            log = {id_tecno_: """REVISAR: VENTA SIN FACTURA"""}
            cls.update_logs_from_imports(
                actualizacion, actualizacion_che, logs=log)
            cls.update_exportado_tecno(id_tecno=id_tecno_, exportado="E")
            return

        for invoice in sale.invoices:
            id_tecno_ = sale.id_tecno
            invoice.accounting_date = sale.sale_date
            invoice.number = sale.number
            invoice.invoice_date = sale.sale_date
            invoice.invoice_type = 'C'
            tipo_numero = sale.number.split('-')

            if sale.description:
                invoice.description = sale.description
            else:
                # Fill description with the type document from tecno
                tbltipodocto = Config.get_tbltipodoctos(tipo_numero[0])
                if tbltipodocto:
                    invoice.description = tbltipodocto[0].TipoDoctos.replace(
                        '\n', ' ').replace('\r', '')

            invoice.save()
            if venta.sw == 2:
                dcto_base = str(venta.Tipo_Docto_Base) + '-' + str(
                    venta.Numero_Docto_Base)
                invoice.reference = dcto_base
                original_invoice = Invoice.search([('number', '=', dcto_base)])
                if original_invoice:
                    invoice.original_invoice = original_invoice[0]
                else:
                    log = {id_tecno_: f"""NO SE ENCONTRO LA FACTURA {dcto_base}
                        PARA CRUZAR CON LA DEVOLUCION {invoice.number}"""}
                    cls.update_logs_from_imports(
                        actualizacion, actualizacion_che, logs=log)
                    cls.update_exportado_tecno(
                        id_tecno=id_tecno_, exportado="E")
                    # Validar porque continua aqui?

            Invoice.validate_invoice([invoice], sw=venta.sw)
            result = cls._validate_total(invoice.total_amount, venta)
            if not result['value']:
                log = {id_tecno_: f"""El total de Tryton {invoice.total_amount} es diferente
                       al total de TecnoCarnes {result['total_tecno']}.
                       La diferencia es de {result['diferencia']}"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                cls.update_exportado_tecno(id_tecno=id_tecno_, exportado="E")
                continue

            try:
                Invoice.post_batch([invoice])
                Invoice.post([invoice])
            except Exception as error:
                if invoice.state == 'posted':
                    # Revert invoice state to validated
                    account_invoice = Table('account_invoice')
                    cursor = Transaction().connection.cursor()
                    cursor.execute(*account_invoice.update(
                        columns=[
                            account_invoice.state,
                        ],
                        values=["validated"],
                        where=account_invoice.id == invoice.id))

                log = {id_tecno_: f"""ERROR: {error}"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                cls.update_exportado_tecno(id_tecno=id_tecno_, exportado="E")
                continue
            if invoice.original_invoice:
                paymentline = PaymentLine()
                paymentline.invoice = invoice.original_invoice
                paymentline.invoice_account = invoice.account
                paymentline.invoice_party = invoice.party
                paymentline.line = invoice.lines_to_pay[0]
                paymentline.save()
                Invoice.reconcile_invoice(invoice)

    @ classmethod
    def _validate_total(cls, total_tryton, venta):
        """ Function to validate difference from tecno and tryton"""

        result = {
            'value': False,
        }
        retencion_causada = abs(venta.retencion_causada)
        total_tecno = abs(venta.valor_total)
        total_tryton = abs(total_tryton)
        total_tecno = total_tecno - retencion_causada
        diferencia = abs(total_tryton - total_tecno)

        if diferencia < Decimal('6.0'):
            result['value'] = True
        result['total_tecno'] = total_tecno
        result['diferencia'] = diferencia
        return result

    @ classmethod
    def set_payment_pos(cls, actualizacion, actualizacion_che, pagos, sale, args_statement):
        """Function to seach paid cash receipts in tecno
            to pay in tryton"""

        pool = Pool()
        Journal = pool.get('account.statement.journal')

        for pago in pagos:
            valor = pago.valor
            id_tecno_ = sale.id_tecno
            if valor == 0:
                log = {
                    id_tecno_: f"""Revisar el valor del pago, su valor es de {valor}"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                cls.update_exportado_tecno(id_tecno=id_tecno_, exportado="E")
                return

            fecha = str(pago.fecha).split()[0].split('-')
            fecha_date = date(int(fecha[0]), int(fecha[1]),
                              int(fecha[2]))
            args_statement['date'] = fecha_date
            journal, = Journal.search([('id_tecno', '=', pago.forma_pago)])
            args_statement['journal'] = journal
            statement, = cls.search_or_create_statement(args_statement)

            if pago.sw == 2 and valor > 0:
                valor = valor * -1

            data_payment = {
                'sales': {
                    sale: valor
                },
                'statement': statement.id,
                'date': fecha_date,
            }
            result_payment = cls.multipayment_invoices_statement(
                actualizacion, actualizacion_che, data_payment)
            if result_payment != 'ok':
                log = {
                    id_tecno_: f"""ERROR AL PROCESAR EL PAGO DE LA VENTA POS {sale.number}"""}
                cls.update_logs_from_imports(
                    actualizacion, actualizacion_che, logs=log)
                # cls.update_exportado_tecno(id_tecno=id_tecno_, exportado="E")
                # Validar aqui porque no se hace una excepcion

    @ classmethod
    def search_or_create_statement(cls, args):
        """Function to search account statement by a sale device
            if it doest not exist, create it"""

        pool = Pool()
        Statement = pool.get('account.statement')
        Device = pool.get('sale.device')

        device = Device(args['device'])
        date = args['date']
        journal = args['journal']
        usuario = args['usuario']
        name_statement = '%s - %s - %s' % (device.rec_name,
                                           journal.rec_name.strip(), usuario)
        statement = Statement.search([('name', '=', name_statement),
                                      ('journal', '=', journal.id),
                                      ('sale_device', '=', device.id),
                                      ('date', '=', date),
                                      ('state', '=', 'draft')])
        if not statement:
            statements_date = Statement.search([
                ('journal', '=', journal.id),
                ('date', '=', date),
                ('sale_device', '=', device.id),
            ])
            turn = len(statements_date) + 1
            values = {
                'name': name_statement,
                'date': date,
                'journal': journal.id,
                'company': device.shop.company.id,
                'start_balance': journal.default_start_balance
                or Decimal('0.0'),
                'end_balance': Decimal('0.0'),
                'turn': turn,
                'sale_device': device.id,
            }
            statement = Statement.create([values])
        return statement

    @ classmethod
    def multipayment_invoices_statement(cls, actualizacion, actualizacion_che, args):
        """Function to pay multiple invoice with
            multiple payment types"""

        pool = Pool()
        Sale = pool.get('sale.sale')
        Configuration = pool.get('account.configuration')
        StatementLine = pool.get('account.statement.line')

        sales = args.get('sales', None)
        statement_id = args.get('statement', None)
        date = args.get('date', None)

        # Build the payment line with the account statement line
        for sale in sales.keys():
            total_paid = Decimal(0.0)
            id_tecno_ = sale.id_tecno
            if sale.payments:
                total_paid = sum([p.amount for p in sale.payments])
                if abs(total_paid) >= abs(sale.total_amount):
                    if total_paid == sale.total_amount:
                        Sale.do_reconcile([sale])
                    else:
                        log = {id_tecno_: f"""Venta pos con un total pagado ({total_paid})
                               mayor al total de la venta ({sale.total_amount})"""}
                        cls.update_logs_from_imports(
                            actualizacion, actualizacion_che, logs=log)
                        # cls.update_exportado_tecno(id_tecno=id_tecno_, exportado="E")
                        # Validar aqui porque no se hace una excepcion
                    continue

            total_pay = args.get('sales')[sale]
            if not total_pay:
                total_pay = sale.total_amount
            else:
                remainder = sale.residual_amount - total_pay
                if abs(remainder) < Decimal(600.0) and remainder != 0:
                    total_pay = sale.residual_amount

            if not sale.invoice or (sale.invoice.state != 'posted'
                                    and sale.invoice.state != 'paid'):
                Sale.post_invoices(sale)

            if not sale.party.account_receivable:
                Party = pool.get('party.party')
                config = Configuration(1)
                if config.default_account_receivable:
                    Party.write([sale.party], {
                        'account_receivable':
                        config.default_account_receivable.id
                    })
                else:
                    cls.update_exportado_tecno(
                        id_tecno=id_tecno_, exportado="E")
                    log = {
                        id_tecno_: """sale_pos.msg_party_without_account_receivable"""}
                    cls.update_logs_from_imports(
                        actualizacion, actualizacion_che, logs=log)
                    continue

            account_id = sale.party.account_receivable.id
            total_pay = Decimal(str(round(total_pay, 2)))
            to_create = {
                'sale': sale.id,
                'date': date,
                'statement': statement_id,
                'amount': total_pay,
                'party': sale.party.id,
                'account': account_id,
                'description': sale.invoice_number or sale.invoice.number
                or '',
            }
            line, = StatementLine.create([to_create])
            write_sale = {
                'turn': line.statement.turn,
            }

            if hasattr(sale, 'order_status'):
                write_sale['order_status'] = 'delivered'

            Sale.write([sale], write_sale)
            if (total_pay + total_paid) == sale.total_amount:
                Sale.do_reconcile([sale])
        return 'ok'

    # Función encargada de obtener los ids de los registros a eliminar
    @ classmethod
    def _get_delete_sales(cls, sales):
        pool = Pool()
        LineStatement = pool.get('account.statement.line')
        AccountMove = pool.get('account.move')

        ids_tecno = []
        to_delete = {
            'sale': [],
            'reconciliation': [],
            'move': [],
            'invoice': [],
            'stock_move': [],
            'shipment': [],
            'shipment_return': [],
            'statement_line': []
        }
        for sale in sales:
            if sale.id_tecno:
                ids_tecno.append(sale.id_tecno)
            else:
                raise UserError("Error Conector",
                                f"No se encontró el id_tecno para {sale}")
            # Se procede a seleccionar las facturas de la venta
            for invoice in sale.invoices:
                if hasattr(invoice, 'electronic_state') and \
                        invoice.electronic_state == 'submitted':
                    raise UserError('account_col.msg_with_electronic_invoice')
                if invoice.state == 'paid':
                    for line in invoice.move.lines:
                        if line.reconciliation and line.reconciliation.id not in to_delete[
                                'reconciliation']:
                            to_delete['reconciliation'].append(
                                line.reconciliation.id)
                if invoice.move:
                    if invoice.move.id not in to_delete['move']:
                        to_delete['move'].append(invoice.move.id)
                if invoice.id not in to_delete['invoice']:
                    to_delete['invoice'].append(invoice.id)
                    line_statement = LineStatement.search([("invoice", "=",
                                                            invoice.id)])
                    if line_statement:
                        account_moves = AccountMove.search([
                            ("id", "=", line_statement[0].move.id)
                        ])
                        if account_moves:
                            to_delete['move'].append(account_moves[0].id)
                            AccountMove.delete_lines(account_moves)

            # Se procede a seleccionar los envíos y movimientos de inventario de la venta
            for line in sale.lines:
                for move in line.moves:
                    if move.id not in to_delete['stock_move']:
                        to_delete['stock_move'].append(move.id)

            for shipment in sale.shipments:
                if shipment.id not in to_delete['shipment']:
                    to_delete['shipment'].append(shipment.id)
                for move in shipment.inventory_moves:
                    if move.id not in to_delete['stock_move']:
                        to_delete['stock_move'].append(move.id)

            for shipment in sale.shipment_returns:
                if shipment.id not in to_delete['shipment_return']:
                    to_delete['shipment_return'].append(shipment.id)
                for move in shipment.inventory_moves:
                    if move.id not in to_delete['stock_move']:
                        to_delete['stock_move'].append(move.id)

            # Se procede a seleccionar las lineas de pago (POS)
            for line in sale.payments:
                if line.id not in to_delete['statement_line']:
                    to_delete['statement_line'].append(line.id)

            if sale.id not in to_delete['sale']:
                to_delete['sale'].append(sale.id)
        return ids_tecno, to_delete

    # Función creada con base al asistente force_draft del módulo sale_pos de presik
    # Esta función se encarga de eliminar los registros mediante cursor
    @ classmethod
    def _delete_sales(cls, to_delete):
        sale_table = Table('sale_sale')
        invoice_table = Table('account_invoice')
        move_table = Table('account_move')
        stock_move_table = Table('stock_move')
        statement_line = Table('account_statement_line')
        shipment_table = Table('stock_shipment_out')
        shipment_return_table = Table('stock_shipment_out_return')
        reconciliation_table = Table('account_move_reconciliation')
        cursor = Transaction().connection.cursor()
        # Se procede a realizar la eliminación de todos los registros
        print(to_delete)
        if to_delete['reconciliation']:
            cursor.execute(*reconciliation_table.delete(
                where=reconciliation_table.id.in_(
                    to_delete['reconciliation'])))

        if to_delete['move']:
            cursor.execute(
                *move_table.update(columns=[move_table.state],
                                   values=['draft'],
                                   where=move_table.id.in_(to_delete['move'])))
            cursor.execute(*move_table.delete(
                where=move_table.id.in_(to_delete['move'])))

        if to_delete['invoice']:
            cursor.execute(*invoice_table.update(
                columns=[invoice_table.state, invoice_table.number],
                values=['validate', None],
                where=invoice_table.id.in_(to_delete['invoice'])))
            cursor.execute(*invoice_table.delete(
                where=invoice_table.id.in_(to_delete['invoice'])))

        if to_delete['stock_move']:
            cursor.execute(*stock_move_table.update(
                columns=[stock_move_table.state],
                values=['draft'],
                where=stock_move_table.id.in_(to_delete['stock_move'])))
            cursor.execute(*stock_move_table.delete(
                where=stock_move_table.id.in_(to_delete['stock_move'])))

        if to_delete['shipment']:
            cursor.execute(*shipment_table.update(
                columns=[shipment_table.state],
                values=['draft'],
                where=shipment_table.id.in_(to_delete['shipment'])))
            cursor.execute(*shipment_table.delete(
                where=shipment_table.id.in_(to_delete['shipment'])))

        if to_delete['shipment_return']:
            cursor.execute(*shipment_return_table.update(
                columns=[shipment_return_table.state],
                values=['draft'],
                where=shipment_return_table.id.in_(
                    to_delete['shipment_return'])))
            cursor.execute(*shipment_return_table.delete(
                where=shipment_return_table.id.in_(
                    to_delete['shipment_return'])))

        if to_delete['statement_line']:
            cursor.execute(*statement_line.delete(
                where=statement_line.id.in_(to_delete['statement_line'])))

        if to_delete['sale']:
            cursor.execute(
                *sale_table.update(columns=[
                    sale_table.state, sale_table.shipment_state,
                    sale_table.invoice_state
                ],
                    values=['draft', 'none', 'none'],
                    where=sale_table.id.in_(to_delete['sale'])))
            cursor.execute(*sale_table.delete(
                where=sale_table.id.in_(to_delete['sale'])))

    # Función encargada de eliminar y marcar para importar ventas de importadas de TecnoCarnes
    @ classmethod
    def delete_imported_sales(cls, sales, cod='N'):
        Cnxn = Pool().get('conector.configuration')
        ids_tecno, to_delete = cls._get_delete_sales(sales)
        cls._delete_sales(to_delete)
        for idt in ids_tecno:
            Cnxn.update_exportado(idt, cod)

    def _get_authorization(self, sale):
        """
            Inheritance function from sale_pos module from presik
            add validation if
        """
        authorization_id = None
        if sale.untaxed_amount_cache:
            if sale.untaxed_amount_cache >= 0:
                if sale.invoice_type == 'P' and sale.shop.pos_authorization:
                    authorization_id = sale.shop.pos_authorization.id
                elif sale.invoice_type == 'M' and sale.shop.manual_authorization:
                    authorization_id = sale.shop.manual_authorization.id
                elif sale.invoice_type == 'C' and sale.shop.computer_authorization:
                    authorization_id = sale.shop.computer_authorization.id
                elif sale.invoice_type in ['1', '2', '3'] and sale.shop.electronic_authorization:
                    authorization_id = sale.shop.electronic_authorization.id
                elif sale.shop.debit_note_electronic_authorization and sale.invoice_type == '92':
                    authorization_id = sale.shop.debit_note_electronic_authorization.id
            else:
                if sale.shop.credit_note_electronic_authorization and sale.invoice_type in ['91', 'N']:
                    authorization_id = sale.shop.credit_note_electronic_authorization.id
            return authorization_id

    def get_sequence(self, sale):
        """
            Inheritance function from sale_pos module from presik
            add validation if
        """
        sequence = None
        if sale.untaxed_amount_cache:
            if sale.untaxed_amount_cache >= 0:
                if sale.invoice_type == 'C' and sale.shop.computer_authorization:
                    sequence = sale.shop.computer_authorization.sequence
                elif sale.invoice_type == 'P' and sale.shop.pos_authorization:
                    sequence = sale.shop.pos_authorization.sequence
                elif sale.invoice_type == 'M' and sale.shop.manual_authorization:
                    sequence = sale.shop.manual_authorization.sequence
                elif sale.invoice_type in ['1', '2', '3'] and sale.shop.electronic_authorization:
                    sequence = sale.shop.electronic_authorization.sequence
                elif sale.shop.invoice_sequence:
                    sequence = sale.shop.invoice_sequence
            else:
                if sale.shop.credit_note_electronic_authorization and sale.invoice_type in ['91', 'N']:
                    sequence = sale.shop.credit_note_electronic_authorization.sequence
                elif sale.shop.debit_note_electronic_authorization and sale.invoice_type == '92':
                    sequence = sale.shop.debit_note_electronic_authorization.sequence
                else:
                    if sale.shop.credit_note_sequence:
                        sequence = sale.shop.credit_note_sequence
            return sequence


class Statement(metaclass=PoolMeta):
    __name__ = 'account.statement'

    @ fields.depends('end_balance')
    def on_change_with_end_balance(self):
        amount = (self.start_balance + sum(line.amount for line in self.lines))
        return amount


# reporte costo de ventas
class SaleShopDetailedCDSStart(ModelView):
    'Sale Shop Detailed Start'
    __name__ = 'sale_shop.sale_detailed_cds.start'
    start_date = fields.Date("From Date",
                             domain=[
                                 If(
                                     Eval('end_date') & Eval('start_date'),
                                     ('start_date', '<=', Eval('end_date')),
                                     ()),
                             ],
                             depends=['end_date'],
                             required=True)
    end_date = fields.Date("To Date",
                           domain=[
                               If(
                                   Eval('start_date') & Eval('end_date'),
                                   ('end_date', '>=', Eval('start_date')), ()),
                               (('end_date', '<=', date.today()))
                           ],
                           depends=['start_date'],
                           required=True)
    company = fields.Many2One('company.company', 'Company', required=True)
    # salesman = fields.Many2One('company.employee', 'Salesman')
    # party = fields.Many2One('party.party', 'Party')
    # product = fields.Many2One('product.product', 'Product')
    # shop = fields.Many2One('sale.shop', 'Shop')

    @ staticmethod
    def default_company():
        return Transaction().context.get('company')


class SaleShopDetailedCDS(Wizard):
    'Sale Shop Detailed'
    __name__ = 'sale_shop.sale_detailed_cds'
    start = StateView('sale_shop.sale_detailed_cds.start',
                      'conector.sale_shop_detailed_start_cds_form', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])

    print_ = StateReport('sale_shop.report_sale_detailed_cds')

    def do_print_(self, action):
        salesman_id = None
        party_id = None
        product_id = None
        shop_id = None

        data = {
            'company': self.start.company.id,
            'start_date': self.start.start_date,
            'end_date': self.start.end_date,
            'salesman': salesman_id,
            'party': party_id,
            'product': product_id,
            'shop': shop_id,
        }

        return action, data

    def transition_print_(self):
        return 'end'


class SaleShopDetailedCDSReport(Report):
    'Sale Shop Detailed Report'
    __name__ = 'sale_shop.report_sale_detailed_cds'

    @ classmethod
    def get_context(cls, records, header, data):
        report_context = super().get_context(records, header, data)
        pool = Pool()
        cursor = Transaction().connection.cursor()
        InvoiceLine = pool.get('account.invoice.line')
        Company = pool.get('company.company')
        MoveLine = pool.get('account.move.line')
        Account = pool.get('account.account')
        Product_uom = pool.get('product.uom')
        Product = pool.get('product.product')
        ProductTemplate = pool.get('product.template')
        Invoice = pool.get('account.invoice')
        Move = pool.get('account.move')
        Party = pool.get('party.party')
        Shop = pool.get('sale.shop')

        product_uom = Product_uom.__table__()
        moveLine = MoveLine.__table__()
        account = Account.__table__()
        invoiceLine = InvoiceLine.__table__()
        party = Party.__table__()
        invoice = Invoice.__table__()
        moves = Move.__table__()
        product = Product.__table__()
        productTemplate = ProductTemplate.__table__()
        shop = Shop.__table__()

        lines = {}

        # Columnas donde se grabaran la consulta que se realiza a las lineas de los movimientos
        columnsMove = {
            'id': moveLine.id,
            'move': moveLine.move,
            'cost': Sum(moveLine.debit - moveLine.credit),
            'reference': moveLine.reference,
            'description': moveLine.description,
            'date': moves.date,
            'party': party.name,
        }

        # Columnas donde se grabaran la consulta que se realiza a las lineas de las facturas
        columnsLine = {
            'move': invoice.move,
            'total_quantity': Sum(invoiceLine.quantity),
            'unit_price': invoiceLine.unit_price,
            'reference': invoice.reference,
            'product_name': invoiceLine.description,
            'invoice_date': invoice.invoice_date,
            'shop': shop.name,
            'unit': product_uom.symbol,
            'state': invoice.state
        }

        # Filtros de busquedas para las lineas de los movimientos
        where = Like(account.code, ('6%'))
        where &= Between(moves.date, data['start_date'], data['end_date'])

        # Consulta que retorna los valores de las lineas de los movimientos
        selectMove = account.join(
            moveLine, 'LEFT', condition=moveLine.account == account.id).join(
                moves, 'LEFT', condition=moveLine.move == moves.id).join(
                    party, 'LEFT',
                    condition=moveLine.party == party.id).select(
                        *columnsMove.values(),
                        where=where,
                        group_by=[
                            moveLine.move,
                            moveLine.id,
                            moveLine.account,
                            moveLine.description,
                            moveLine.reference,
                            moves.date,
                            party.name,
                        ])
        # Ejecucion de la consulta
        cursor.execute(*selectMove)

        resultMove = cursor.fetchall()

        fila_dict_move = {}

        # Verificamos que la consulta traiga informacion
        if resultMove:

            for index, record in enumerate(resultMove):
                fila_dict_move = OrderedDict(
                )  # Le damos la extructura de diccionario
                fila_dict_move = dict(zip(columnsMove.keys(), record))

                move = fila_dict_move['move']
                reference = fila_dict_move['reference']
                description = fila_dict_move['description']
                cost = fila_dict_move['cost']
                date = fila_dict_move['date']
                party = fila_dict_move['party']

                if move not in lines:
                    lines[move] = {'lines': {}}

                if description not in lines[move]['lines']:
                    lines[move]['lines'][description] = {
                        'party': party,
                        'unit_price': 0,
                        'total_quantity': 0,
                        'cost': 0,
                        'reference': reference,
                        'date': date,
                        'shop': '',
                        'total_cost': 0,
                        'state': '',
                        'unit': ''
                    }

                lines[move]['lines'][description]['cost'] += cost

        # FIltros para la consulta a las lineas de las facturas
        where = Between(invoice.invoice_date, data['start_date'],
                        data['end_date'])
        where &= invoice.state.in_(['paid', 'validated', 'posted'])
        where &= invoice.type.in_(['out'])

        # Consulta que retorna la informacion de las lineas de las facturas
        selectLine = invoice.join(
            invoiceLine, 'LEFT',
            condition=invoiceLine.invoice == invoice.id).join(
                product, 'LEFT',
                condition=invoiceLine.product == product.id).join(
                    productTemplate,
                    'LEFT',
                    condition=product.template == productTemplate.id).join(
                        shop, 'LEFT', condition=invoice.shop == shop.id).join(
                            product_uom,
                            'LEFT',
                            condition=invoiceLine.unit
                            == product_uom.id).select(
                                *columnsLine.values(),
                                where=where,
                                group_by=[
                                    invoice.move, invoice.description,
                                    invoice.reference, invoiceLine.unit_price,
                                    invoiceLine.description,
                                    invoice.invoice_date, shop.name,
                                    product_uom.symbol, invoice.state
                                ])

        cursor.execute(*selectLine)

        resultLine = cursor.fetchall()

        fila_dict_line = {}

        # Verificamos que la consulta halla traifo informacion
        if resultLine:

            for record in resultLine:

                fila_dict_line = OrderedDict(
                )  # Le damos la extructura de diccionario
                fila_dict_line = dict(zip(columnsLine.keys(), record))

                move = fila_dict_line['move']
                reference = fila_dict_line['reference']
                description = fila_dict_line['product_name']
                unit_price = fila_dict_line['unit_price']
                total_quantity = fila_dict_line['total_quantity']
                shop = fila_dict_line['shop']
                unit = fila_dict_line['unit']
                state = fila_dict_line['state']

                if move in lines:
                    if description in lines[move]['lines']:

                        lines[move]['lines'][description]['shop'] = shop
                        lines[move]['lines'][description][
                            'unit_price'] = unit_price
                        lines[move]['lines'][description][
                            'total_quantity'] += Decimal(total_quantity)
                        lines[move]['lines'][description]['unit'] = unit
                        lines[move]['lines'][description]['state'] = state

            # For que recorreo las lineas creadas con las lineas de movimiento y factura y realiza la operacion
            # para dar el costo unitario, si este es 0 aplica un 0
            for key, record in lines.items():
                for description, line in lines[key]['lines'].items():
                    line['total_cost'] = round(
                        line['cost'] / line['total_quantity'],
                        2) if line['cost'] != 0 and line[
                            'total_quantity'] != 0 else line['cost']

        report_context['records'] = lines
        report_context['start_date'] = data['start_date']
        report_context['end_date'] = data['end_date']
        report_context['company'] = Company(data['company'])
        return report_context


class SaleInvoiceValueCdstStart(ModelView):
    'Sale Invoice Values View Report'
    __name__ = 'sale.invoice_values_cdst.start'
    company = fields.Many2One('company.company', 'Company', required=True)
    from_date = fields.Date('From Date', required=True)
    to_date = fields.Date('To Date', required=True)
    document_type = fields.Selection('get_document_type', 'Type Document')
    # state = fields.Selection(STATES, 'State')

    @ staticmethod
    def default_company():
        return Transaction().context.get('company')

    def get_document_type():
        pool = Pool()
        Config = pool.get('conector.configuration')
        condition = "(tipo=1 OR tipo=2)"
        consultc = "SET DATEFORMAT ymd "\
            "SELECT idTipoDoctos FROM TblTipoDoctos "\
            f"WHERE {condition} "
        result_tecno = Config.get_data(consultc)
        list_document = [row[0] for row in result_tecno]
        TYPE_DOCUMENT = [(val, val) for val in list_document]
        return TYPE_DOCUMENT


class SaleInvoiceValueCdst(Wizard):
    'Sale Invoice Values Wizard'
    __name__ = 'sale.invoice_values_cdst'
    start = StateView('sale.invoice_values_cdst.start',
                      'conector.form_view_invoice_values_cdst_start', [
                          Button('Cancel', 'end', 'tryton-cancel'),
                          Button('Print', 'print_', 'tryton-ok', default=True),
                      ])
    print_ = StateReport('sale.invoice_values_cdst.report')

    def do_print_(self, action):
        """Function to save form values and return to build report"""

        from_date = self.start.from_date
        to_date = self.start.to_date
        if (to_date - from_date).days > 31:
            raise UserError(
                'El rango de fecha no puede exceder mas de 31 dias.')

        data = {
            'company': self.start.company.id,
            'from_date': from_date,
            'to_date': to_date,
            'type_document': self.start.document_type,
            # 'state': self.start.state,
        }
        return action, data


class SaleInvoiceValueCdstReport(Report):
    'Sale Invoice Values Report'
    __name__ = 'sale.invoice_values_cdst.report'

    @ classmethod
    def get_context(cls, records, header, data):
        """Function that take context of report and import it"""
        report_context = super().get_context(records, header, data)

        pool = Pool()
        Company = pool.get('company.company')
        Sale = pool.get('sale.sale')

        info_invoices = []
        type_document = ""
        state = ""
        total_amount_tecno = Decimal(0)
        total_amount_tryton = Decimal(0)
        total_amount_tax_tecno = Decimal(0)
        init_date = data["from_date"]
        end_date = data["to_date"]

        # build init domain
        domain_sales = [("sale_date", ">=", init_date),
                        ("sale_date", "<=", end_date),
                        ("state", "!=", "draft")]

        # validate if type document was selected and add to domain
        if data["type_document"]:
            type_document = data["type_document"]
            domain_sales.append(("number", "ilike", f"{type_document}-%"))

        sales = Sale.search(domain_sales)

        if sales:
            for sale in sales:
                invoices = {}
                invoice_difference = 0
                if sale.invoice:
                    invoice_amount_tecno = sale.invoice_amount_tecno
                    tax_amount_tecno = sale.tax_amount_tecno
                    invoice_value_tryton = sale.invoice.total_amount
                    total_amount_tax_tecno += tax_amount_tecno
                    if invoice_amount_tecno is not None\
                            and invoice_value_tryton is not None:

                        invoice_amount_tecno = Decimal(
                            abs(invoice_amount_tecno))
                        invoice_value_tryton = Decimal(
                            abs(invoice_value_tryton))
                        tax_amount_tecno = Decimal(abs(tax_amount_tecno))

                        invoice_difference = invoice_amount_tecno \
                            - invoice_value_tryton

                        invoice_difference = Decimal(abs(invoice_difference))
                        total_amount_tecno += invoice_amount_tecno
                        total_amount_tryton += invoice_value_tryton

                        if invoice_difference > 5:
                            invoices = {
                                "date": sale.sale_date,
                                "reference": sale.reference,
                                "description": sale.invoice.description,
                                "value_tecno": invoice_amount_tecno,
                                "value_tryton": invoice_value_tryton,
                                "difference": invoice_difference,
                                "tax_amount": tax_amount_tecno,
                            }
                            info_invoices.append(invoices)
            total_difference = abs(total_amount_tecno - total_amount_tryton)

        if not sales:
            raise UserError(
                message="SIN INFORMACION",
                description="No hay documentos en el rango de fecha"
                "con inconsistencias.")

        report_context['info_report'] = info_invoices
        report_context['company'] = Company(data['company'])
        report_context['type'] = type_document
        report_context['total_tecno'] = total_amount_tecno
        report_context['total_tryton'] = total_amount_tryton
        report_context['state'] = state
        report_context['total_difference'] = total_difference
        report_context['total_amount_tax_tecno'] = total_amount_tax_tecno
        return report_context
