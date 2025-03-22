import json
import jwt
import time
from trytond.model import ModelSingleton, ModelSQL, ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.rpc import RPC
from trytond.exceptions import UserError

class MetabaseConfiguration(ModelSingleton, ModelSQL, ModelView):
    """Configuración de Metabase"""
    __name__ = "metabase.configuration"
    name = fields.Char("NombreConexion", required=True)
    metabase_url = fields.Char("URL de Metabase", required=True)
    api_key = fields.Char("Secret API Key", required=True)

class MetabaseAccess(ModelSQL, ModelView):
    """Metabase Access"""
    __name__ = 'metabase.access'

    name = fields.Char("Name", required=True)
    dashboard_id = fields.Integer("Dashboard ID", required=True)
    params = fields.Text("Parameters")
    expiration = fields.Date("Expiration Date")
    allowed_groups = fields.Many2Many(
        "metabase.access-res.group", "access", "group", "Allowed Groups"
    )

    @classmethod
    def search(cls, domain, offset=0, limit=None, order=None, count=False):
        """Filtra los dashboards según los grupos permitidos"""
        pool = Pool()
        User = pool.get("res.user")
        user = User(Transaction().user)

        groups = {g.id for g in user.groups}
        domain.append(('allowed_groups', 'in', list(groups)))

        return super().search(domain, offset, limit, order, count)

    @classmethod
    def __setup__(cls):
        """Configurar los botones del modelo"""
        super().__setup__()
        cls._buttons.update({'generate_url': {'readonly': False}})

    @classmethod
    @ModelView.button
    def generate_url(cls, records):
        """Genera y abre la URL del dashboard en Metabase"""
        pool = Pool()
        config_model = pool.get("metabase.configuration")
        metabase_config = config_model.search([], limit=1)

        if not metabase_config:
            raise UserError("Metabase no está configurado correctamente.")

        metabase_config = metabase_config[0]
        base_url = metabase_config.metabase_url.rstrip("/")  # Eliminar '/' al final si existe

        for record in records:
            try:
                params = json.loads(record.params) if record.params and record.params.strip() else {}
            except json.JSONDecodeError:
                raise UserError("Los parámetros de Metabase deben ser un JSON válido.")

            payload = {
                "resource": {"dashboard": record.dashboard_id},
                "params": params,
                "exp": int(time.time()) + 600  # Expira en 10 minutos
            }

            # Generar el token correctamente
            token = jwt.encode(payload, metabase_config.api_key, algorithm="HS256")
            if isinstance(token, bytes):  # Compatibilidad con Python 3+
                token = token.decode('utf-8')

            # Construir la URL correctamente
            url = f"{base_url}/embed/dashboard/{token}#bordered=true&titled=true"

            return {
                'id': 'action_open_dashboard',
                'type': 'ir.action.url',
                'url': url,
                'target': 'new'
            }

class MetabaseAccessResGroup(ModelSQL):
    """Tabla intermedia para la relación Many2Many entre metabase.access y res.group"""
    __name__ = "metabase.access-res.group"

    access = fields.Many2One("metabase.access", "Metabase Access", required=True, ondelete="CASCADE")
    group = fields.Many2One("res.group", "Group", required=True, ondelete="CASCADE")
