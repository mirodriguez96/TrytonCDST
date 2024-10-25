from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction


# Heredar para agregar el campo id_tecno
class SaleDevice(metaclass=PoolMeta):
    'SaleDevice'
    __name__ = 'sale.device'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)

    @classmethod
    def import_data_pos(cls):
        print("RUN CONFIG POS")
        # Se requiere previamente haber creado el diario para ventas POS con código VM
        # Posterior a la importación. revisar las configuraciones
        pool = Pool()
        Actualizacion = pool.get('conector.actualizacion')
        actualizacion = Actualizacion.create_or_update("CONFIG_POS")
        logs = {}
        try:
            cls.import_sale_shop(logs)
            cls.import_sale_device(logs)
            cls.import_statement_sale(logs)
        except Exception as e:
            Transaction().rollback()
            logs['CONFIG_POS'] = f"EXCEPCION: {str(e)}"
        actualizacion.add_logs(logs)
        print("FINISH CONFIG POS")

    # Se importan las tiendas que seran utilizadas para las ventas POS
    @classmethod
    def import_sale_shop(cls, logs):
        pool = Pool()
        Config = pool.get('conector.configuration')
        Shop = pool.get('sale.shop')
        Location = pool.get('stock.location')
        payment_term = pool.get('account.invoice.payment_term')
        payment_term, = payment_term.search([],
                                            order=[('id', 'DESC')],
                                            limit=1)
        currency = pool.get('currency.currency')
        moneda, = currency.search([('code', '=', 'COP')])
        # Se concuerda que las bodegas de SqlServer (TecnoCarnes) equivalen a las tiendas en Tryton
        bodegas = Config.get_data_table('TblBodega')
        for bodega in bodegas:
            try:
                id_tecno = bodega.IdBodega
                location = Location.search([('id_tecno', '=', id_tecno)])
                if not location:
                    msg = f"LA BODEGA DE TECNOCARNES CON ID {id_tecno} NO EXISTE"
                    logs[id_tecno] = msg
                nombre = bodega.Bodega
                location = location[0]
                existe = Shop.search([('warehouse', '=', location)])
                company = Transaction().context.get('company')
                if not existe:
                    shop = {
                        'name': nombre,
                        'warehouse': location.id,
                        'currency': moneda,
                        'company': company,
                        'payment_term': payment_term,
                        'sale_invoice_method': 'order',
                        'sale_shipment_method': 'order'
                    }
                    shop = cls.sequence_sale(shop)
                    shop = cls.price_list_sale(shop)
                    Shop.create([shop])
            except Exception as error:
                Transaction().rollback()
                logs[id_tecno] = f"EXCEPCION:{error}"

    # Se crea una lista de precios para las tiendas a importar
    @classmethod
    def price_list_sale(cls, shop):
        pool = Pool()
        Price_list = pool.get('product.price_list')
        price_list = Price_list.search([], order=[('id', 'DESC')], limit=1)

        if price_list:
            shop['price_list'] = price_list[0]
        else:
            price_list = {
                'name': 'Lista de precio POS',
                'company': 1,
                'unit': 'product_default'
            }
            price_list, = Price_list.create([price_list])
            shop['price_list'] = price_list
        return shop

    # Crear secuencia para las ventas
    @classmethod
    def sequence_sale(cls, shop):
        pool = Pool()
        Sequence = pool.get('ir.sequence')
        sequence_t = cls.find_seq('Sale')
        sequence1 = Sequence.search([('sequence_type', '=', sequence_t[0])])
        if sequence1:
            shop['sale_sequence'] = sequence1[0]
            shop['sale_return_sequence'] = sequence1[0]
        else:
            sequence2 = {
                'name': 'Venta',
                'number_increment': 1,
                'number_next_internal': 1,
                'padding': 0,
                'sequence_type': sequence_t,
                'type': 'incremental'
            }
            sequence2, = Sequence.create([sequence2])
            shop['sale_sequence'] = sequence2
            shop['sale_return_sequence'] = sequence2
        return shop

    # Función encargada de consultar la secuencia de un nombre dado
    @classmethod
    def find_seq(cls, name):
        Sequence = Pool().get('ir.sequence.type')
        seq = Sequence.__table__()
        cursor = Transaction().connection.cursor()
        cursor.execute(*seq.select(where=(seq.name == name)))
        result = cursor.fetchall()
        return result[0]

    # CREAR TERMINALES DE VENTA
    @classmethod
    def import_sale_device(cls, logs):
        pool = Pool()
        Config = pool.get('conector.configuration')
        SaleDevice = pool.get('sale.device')
        Journal = pool.get('account.statement.journal')
        Shop = pool.get('sale.shop')
        equipos = Config.get_data_table('TblEquipo')
        bodegas = Config.get_data_table('TblBodega')

        devices = []
        for equipo in equipos:
            for bodega in bodegas:
                try:
                    id_tecno = equipo.IdEquipo + '-' + str(bodega.IdBodega)
                    nombre = equipo.Equipo + ' - ' + bodega.Bodega
                    shop = Shop.search([('warehouse.id_tecno', '=',
                                        bodega.IdBodega)])
                    if not shop:
                        shop = Shop.search([], order=[('id', 'DESC')], limit=1)
                    # En caso de ser un nombre vacio se continua con el siguiente
                    if len(equipo.Equipo) == 0 or equipo.Equipo == ' ':
                        msg = f"EL NOMBRE DEL EQUIPO ESTA VACIO {equipo.IdEquipo}"
                        logs[id_tecno] = msg
                        break

                    journals = Journal.search([()])
                    device = SaleDevice.search([
                        'OR', ('id_tecno', '=', id_tecno),
                        [
                            'AND', ('id_tecno', '=', equipo.IdEquipo),
                            ('shop.warehouse.id_tecno', '=', bodega.IdBodega)
                        ]
                    ])
                    if not device:
                        sale_data = {
                            'id_tecno': id_tecno,
                            'name': nombre,
                            'code': id_tecno,
                            'shop': shop[0].id,
                            'environment': 'retail'
                        }
                        devices.append(SaleDevice.create([sale_data]))
                    else:
                        device, = device
                        if not device.journals and journals:
                            device.journals = journals
                            device.save()
                except Exception as error:
                    Transaction().rollback()
                    logs[id_tecno] = f'EXCEPCION: {error}'
        for device in devices:
            if not device.journals and journals:
                device.journals = journals
                device.save()

    # Libro de Ventas Pos
    @classmethod
    def import_statement_sale(cls, logs):
        pool = Pool()
        Config = pool.get('conector.configuration')
        StatementJournal = pool.get('account.statement.journal')
        PayMode = pool.get('account.voucher.paymode')
        forma_pago = Config.get_data_table('TblFormaPago')
        for fp in forma_pago:
            try:
                id_tecno = str(fp.IdFormaPago)
                exists = StatementJournal.search([('id_tecno', '=', id_tecno)])
                if not exists:
                    paymode = PayMode.search([('id_tecno', '=', id_tecno)])
                    if not paymode:
                        msg = f"NO SE ENCONTRO EN TRYTON EL MODO DE PAGO {id_tecno}"
                        logs[id_tecno] = msg
                        continue
                    paymode, = paymode
                    statement_journal = {
                        'id_tecno': id_tecno,
                        'name': fp.FormaPago,
                        'journal': paymode.journal.id,
                        'account': paymode.account.id,
                        'payment_means_code': paymode.payment_means_code,
                        'kind': 'other',
                    }
                    StatementJournal.create([statement_journal])
            except Exception as error:
                Transaction().rollback()
                logs[id_tecno] = f"EXCEPCION: {error}"


# Heredar para agregar el campo id_tecno
class Journal(metaclass=PoolMeta):
    'StatementJournal'
    __name__ = 'account.statement.journal'
    id_tecno = fields.Char('Id Tabla Sqlserver', required=False)
