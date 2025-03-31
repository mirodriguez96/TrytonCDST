import math
from decimal import Decimal

from trytond.exceptions import UserError
from trytond.pool import Pool
from trytond.transaction import Transaction


# Función encargada de convertir una lista a un string tipo tupla
def list_to_tuple(value, string=False):
    result = None
    if value:
        if string:
            result = "('" + "', '".join(map(str, value)) + "')"
        else:
            result = "(" + ", ".join(map(str, value)) + ")"
    return result


# Se retorna las cuentas analiticas según los tipos de documentos que coinciden
def get_analytic_types(tipos_doctos):
    analytic_types = {}
    if tipos_doctos:
        pool = Pool()
        Config = pool.get('conector.configuration')
        ids_tipos = list_to_tuple(tipos_doctos)
        tbltipodocto = Config.get_tbltipodoctos_encabezado(ids_tipos)
        _values = {}
        for tipodocto in tbltipodocto:
            if tipodocto.Encabezado and tipodocto.Encabezado != '0':
                encabezado = str(tipodocto.Encabezado)
                idtipod = str(tipodocto.idTipoDoctos)
                if encabezado not in _values:
                    _values[encabezado] = []
                _values[encabezado].append(idtipod)
        if _values:
            AnalyticAccount = pool.get('analytic_account.account')
            analytic_accounts = AnalyticAccount.search([('code', 'in',
                                                         _values.keys())])
            for ac in analytic_accounts:
                idstipo = _values[ac.code]
                for idt in idstipo:
                    analytic_types[idt] = ac
    return analytic_types


# Se retorna un diccionario con las ubicaciones encontradas
def get_locations(bodegas):
    result = {}
    if bodegas:
        Location = Pool().get('stock.location')
        locations = Location.search([('id_tecno', 'in', bodegas)])
        for l in locations:
            result[l.id_tecno] = l
    return result


# Se valida y retorna el centro de operacion encontrado
def get_operation_center(cls):
    operation_center = hasattr(cls, 'operation_center')
    if operation_center:
        OperationCenter = Pool().get('company.operation_center')
        operation_center = OperationCenter.search([],
                                                  order=[('id', 'DESC')],
                                                  limit=1)
        if not operation_center:
            raise UserError("operation_center",
                            "the operation center is missing")
        operation_center, = operation_center
    return operation_center


#
def get_products(values):
    result = {}
    if values:
        Product = Pool().get('product.product')
        products = Product.search(
            [['OR', ('id_tecno', 'in', values), ('code', 'in', values)],
             ('active', '=', True)])
        for p in products:
            result[p.code] = p
    return result


def validate_documentos(data):
    """Function to validate documetns from internal shipments"""

    pool = Pool()
    Config = pool.get('conector.configuration')
    Actualizacion = pool.get('conector.actualizacion')
    actualizacion = Actualizacion.create_or_update(
        'CREAR ENVIOS INTERNOS VALIDACION DE PERIODOS')
    logs = {}
    dictprodut = {}
    to_exception = []
    exists = []
    tipos_doctos = []
    bodegas = []
    productos = []
    selecto_product = []

    result = {
        "tryton": {},
        "logs": {},
        "exportado": {
            "T": [],
            "E": [],
        },
    }
    Internal = pool.get('stock.shipment.internal')
    operation_center = get_operation_center(Internal)
    id_company = Transaction().context.get('company')
    shipments = Internal.search([('id_tecno', '!=', None)])

    for ship in shipments:
        exists.append(ship.id_tecno)

    for p in data:
        if p.IdProducto not in selecto_product:
            selecto_product.append(p.IdProducto)

    selecto_product = tuple(selecto_product)

    if len(selecto_product) <= 1:
        selecto_product = f'({selecto_product[0]})'

    select = f"SELECT tr.IdProducto, tr.IdResponsable \
                FROM TblProducto tr \
                WHERE tr.IdProducto in {selecto_product};"

    set_data = Config.get_data(select)

    for item in set_data:

        dictprodut[item[0]] = {
            'idresponsable': str(item[1]),
        }

    move = {}
    for value, d in enumerate(data):
        tipo = str(d.tipo)
        reference = f"{tipo}-{d.Numero_Documento}"
        reference_ = f"{d.notas}"
        id_tecno = f"{d.sw}-{reference}"

        if id_tecno in exists:
            result["logs"][id_tecno] = "Ya existe en Tryton"
            result["exportado"]["T"].append(id_tecno)
            continue
        fecha_documento = d.Fecha_Documento.date()
        if id_tecno not in result["tryton"]:
            shipment = {
                "id_tecno": id_tecno,
                "reference": reference_,
                "number": reference,
                "planned_date": fecha_documento,
                "effective_date": fecha_documento,
                "planned_start_date": fecha_documento,
                "effective_start_date": fecha_documento,
                "company": id_company,
            }
            if operation_center:
                shipment["operation_center"] = operation_center.id
            if tipo not in tipos_doctos:
                tipos_doctos.append(tipo)
            id_bodega = str(d.from_location)
            if id_bodega not in bodegas:
                bodegas.append(id_bodega)
            id_bodega_destino = str(d.IdBodega)
            if id_bodega_destino not in bodegas:
                bodegas.append(id_bodega_destino)
            shipment["from_location"] = id_bodega
            shipment["to_location"] = id_bodega_destino
            result["tryton"][id_tecno] = shipment
            # to_create.append(shipment) #
        shipment = result["tryton"][id_tecno]
        if "moves" not in shipment:
            shipment["moves"] = []
        # Se crea el movimiento
        producto = dictprodut[d.IdProducto]['idresponsable'] if dictprodut[
            d.IdProducto] and dictprodut[
                d.IdProducto]['idresponsable'] != '0' else str(d.IdProducto)
        if producto not in productos:
            productos.append(producto)
        quantity = round(float(round(d.Cantidad_Facturada, 3)), 3)

        if quantity < 0:
            result["logs"][
                id_tecno] = f"Cantidad en negativo: {quantity} Producto: {producto}"
            result["exportado"]["E"].append(id_tecno)
            del (result["tryton"][id_tecno])
            continue

        if id_tecno not in move:
            move[id_tecno] = {'move_product': {}}
        if producto not in move[id_tecno]['move_product']:

            move[id_tecno]['move_product'][producto] = {
                "from_location": shipment["from_location"],
                "to_location": shipment["to_location"],
                "product": producto,
                "company": id_company,
                "quantity": round(float(0), 3),
                "planned_date": shipment["planned_date"],
                "effective_date": shipment["effective_date"],
            }

        quantity_float = move[id_tecno]['move_product'][producto]["quantity"]
        move[id_tecno]['move_product'][producto]["quantity"] = round(
            quantity + quantity_float, 3)

    for id_tec, line_move in result['tryton'].items():

        if result['tryton'][id_tec]:
            result['tryton'][id_tec]['moves'] = [
                ('create', [i for i in move[id_tec]['move_product'].values()])
            ]

    products = get_products(productos)
    locations = get_locations(bodegas)
    analytic_types = None
    if hasattr(Internal, 'analytic_account') and tipos_doctos:
        analytic_types = get_analytic_types(tipos_doctos)
    for id_tecno, shipment in result["tryton"].items():
        if analytic_types:
            # tipo = shipment["reference"].split("-")[0]
            tipo = shipment["number"].split("-")[0]
            if tipo in analytic_types:
                shipment["analytic_account"] = analytic_types[tipo].id
            else:
                result["logs"][
                    id_tecno] = f"No se encontro la cuenta analitica para el tipo: {tipo}"
                result["exportado"]["E"].append(id_tecno)
                continue
        from_location = shipment["from_location"]
        if from_location in locations:
            storage_location_id = locations[from_location].storage_location.id
            shipment["from_location"] = storage_location_id
        else:
            result["tryton"][
                id_tecno] = f"No se encontro la bodega con id_tecno: {from_location}"
            result["exportado"]["E"].append(id_tecno)
            continue
        to_location = shipment["to_location"]
        if to_location in locations:
            storage_location_id = locations[to_location].storage_location.id
            shipment["to_location"] = storage_location_id
        else:
            result["tryton"][
                id_tecno] = f"No se encontro la bodega con id_tecno: {to_location}"
            result["exportado"]["E"].append(id_tecno)
            continue
        products_exist = True
        for mv in shipment["moves"][0][1]:
            mv["from_location"] = shipment["from_location"]
            mv["to_location"] = shipment["to_location"]
            if mv["product"] in products:
                product = products[mv["product"]]
                mv["uom"] = product.default_uom.id
                mv["product"] = product.id
                if product.default_uom.symbol.upper() == 'U':
                    mv["quantity"] = round(float(int(mv["quantity"])), 3)
            else:
                products_exist = False
                result["logs"][
                    id_tecno] = f"No se encontro el producto: {mv['product']}"
                break
        if not products_exist:
            result["exportado"]["E"].append(id_tecno)
            continue
        # result["exportado"]["T"].append(id_tecno)
    for to_delete in result["exportado"]["E"]:
        if to_delete in result["tryton"]:
            del (result["tryton"][to_delete])
    if to_exception:
        actualizacion.add_logs(logs)
    return result
