from flask import Blueprint

# Crear el blueprint principal
main_bp = Blueprint('main', __name__)

# Importar todos los módulos después de crear el blueprint
from . import r_home
from . import r_acceso
from . import r_empleados
from . import r_proveedores
from . import r_agenda
from . import r_almacen
from . import r_campanas
from . import r_clientes
from . import r_compras
from . import r_pedidos
from . import r_ventas
from . import r_usuarios