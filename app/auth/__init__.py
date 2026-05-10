"""
Módulo de autenticación.

Exporta:
    init_auth(app)     → registra JWT callbacks + blueprint /auth
    jwt_requerido      → decorator: requiere JWT válido
    rol_requerido      → decorator: requiere rol específico
    permiso_requerido  → decorator: requiere permiso específico
    requiere_empleado  → decorator: solo para empleados (no clientes)
    get_usuario_actual → helper: retorna claims del JWT actual
"""

from .routes import auth_bp
from .callbacks import init_callbacks
from .decorators import (
    jwt_requerido,
    rol_requerido,
    permiso_requerido,
    requiere_empleado,
    get_usuario_actual
)


def init_auth(app):
    """
    Inicializa el módulo de autenticación.
    Llamar desde la factory function create_app().
    """
    init_callbacks(app)


__all__ = [
    "init_auth",
    "jwt_requerido",
    "rol_requerido",
    "permiso_requerido",
    "requiere_empleado",
    "get_usuario_actual",
]