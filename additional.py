from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.exceptions import UserError

# Función encargada de convertir una lista a un string tipo tupla
def list_to_tuple(value):
    result = None
    if value:
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
        _codes = {}
        for tipodocto in tbltipodocto:
            if tipodocto.Encabezado != '0':
                _codes[str(tipodocto.Encabezado)] = str(tipodocto.idTipoDoctos)
                # _codes.append(str(tipodocto.Encabezado))
        if _codes:
            AnalyticAccount = pool.get('analytic_account.account')
            analytic_accounts = AnalyticAccount.search([('code', 'in', _codes.keys())])
            for ac in analytic_accounts:
                analytic_types[_codes[ac.code]] = ac
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
        operation_center = OperationCenter.search([], order=[('id', 'DESC')], limit=1)
        if not operation_center:
            raise UserError("operation_center", "the operation center is missing")
        operation_center, = operation_center
    return operation_center

#
def get_products(values):
    result = {}
    if values:
        Product = Pool().get('product.product')
        products = Product.search([('id_tecno', 'in', values)])
        for p in products:
            result[p.code] = p
    return result

#
def validate_documentos(data):
    result = {
        "tryton": {},
        "logs": {},
        "exportado": {
            "T": [],
            "E": [],
        },
    }
    pool = Pool()
    Internal = pool.get('stock.shipment.internal')
    # Verificar y seleccionar el primer centro de operaciones
    operation_center = get_operation_center(Internal)
    id_company = Transaction().context.get('company')
    tipos_doctos = []
    bodegas = []
    productos = []
    # to_create = []
    for d in data:
        tipo = str(d.tipo)
        reference = f"{tipo}-{d.Numero_Documento}"
        id_tecno = f"{d.sw}-{reference}"
        fecha_documento = d.Fecha_Documento.date()
        if id_tecno not in result["tryton"]:
            shipment = {
                "id_tecno": id_tecno,
                "reference": reference,
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
            # Se agrega al diccionario
            result["tryton"][id_tecno] = shipment
            # to_create.append(shipment) #
        shipment = result["tryton"][id_tecno]
        moves = []
        if "moves" not in shipment:
            shipment["moves"] = [('create', moves)]
        else:
            moves = shipment["moves"][0][1]
        # Se crea el movimiento
        producto = str(d.IdProducto)
        if producto not in productos:
            productos.append(producto)
        move = {
            "from_location": shipment["from_location"],
            "to_location": shipment["to_location"],
            "product": producto,
            "company": id_company,
            "quantity": float(d.Cantidad_Facturada),
            "planned_date": shipment["planned_date"],
            "effective_date": shipment["effective_date"],
        }
        moves.append(move)
    products = get_products(productos)
    locations = get_locations(bodegas)
    analytic_types = None
    if hasattr(Internal, 'analytic_account') and tipos_doctos:
        analytic_types = get_analytic_types(tipos_doctos)
    for id_tecno, shipment in result["tryton"].items():
        from_location = shipment["from_location"]
        if from_location in locations:
            storage_location_id = locations[from_location].storage_location.id
            shipment["from_location"] = storage_location_id
        else:
            result["tryton"][id_tecno] = f"No se encontro la bodega con id_tecno: {from_location}"
            result["exportado"]["E"].append(id_tecno)
            del(result["tryton"][id_tecno])
            continue
        to_location = shipment["to_location"]
        if to_location in locations:
            storage_location_id = locations[to_location].storage_location.id
            shipment["to_location"] = storage_location_id
        else:
            result["tryton"][id_tecno] = f"No se encontro la bodega con id_tecno: {to_location}"
            result["exportado"]["E"].append(id_tecno)
            del(result["tryton"][id_tecno])
            continue
        for mv in shipment["moves"][0][1]:
            mv["from_location"] = shipment["from_location"]
            mv["to_location"] = shipment["to_location"]
            if mv["product"] in products:
                mv["uom"] = products[mv["product"]].default_uom.id
                mv["product"] = products[mv["product"]].id
            else:
                result["logs"][id_tecno] = f"No se encontro el producto: {mv['product']}"
                break
        if id_tecno in result["logs"]:
            result["exportado"]["E"].append(id_tecno)
            del(result["tryton"][id_tecno])
            continue
        # Analytic
        if analytic_types:
            tipo = shipment["reference"].split("-")[0]
            if tipo in analytic_types:
                shipment["analytic_account"] = analytic_types[tipo].id
            else:
                result["tryton"][id_tecno] = f"No se encontro la cuenta analitica para el tipo: {tipo}"
                result["exportado"]["E"].append(id_tecno)
                del(result["tryton"][id_tecno])
                continue
        result["exportado"]["T"].append(id_tecno)
    return result