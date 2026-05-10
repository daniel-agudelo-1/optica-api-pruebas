from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt

import os
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"


def jwt_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not AUTH_ENABLED:
            return f(*args, **kwargs)

        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({
                "success": False,
                "error": "Token requerido o inválido",
                "message": "Debes iniciar sesión para acceder a este recurso"
            }), 401

        return f(*args, **kwargs)
    return decorated


def rol_requerido(*roles_permitidos):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not AUTH_ENABLED:
                return f(*args, **kwargs)

            try:
                verify_jwt_in_request()
                claims = get_jwt()
                rol_usuario = claims.get('rol', '').lower().strip()

                if rol_usuario not in [r.lower() for r in roles_permitidos]:
                    return jsonify({
                        "success": False,
                        "error": "Acceso denegado",
                        "message": f"No tienes el rol necesario para acceder a este recurso."
                    }), 403

            except Exception:
                return jsonify({
                    "success": False,
                    "error": "Token requerido o inválido",
                    "message": "Debes iniciar sesión para acceder a este recurso"
                }), 401

            return f(*args, **kwargs)
        return decorated
    return decorator


def permiso_requerido(permiso: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not AUTH_ENABLED:
                return f(*args, **kwargs)

            try:
                verify_jwt_in_request()
                claims = get_jwt()
                permisos_usuario = claims.get('permisos', [])

                if permiso not in permisos_usuario:
                    return jsonify({
                        "success": False,
                        "error": "Permiso insuficiente",
                        "message": f"No tienes el permiso necesario para acceder a este recurso."
                    }), 403

            except Exception:
                return jsonify({
                    "success": False,
                    "error": "Token requerido o inválido",
                    "message": "Debes iniciar sesión para acceder a este recurso"
                }), 401

            return f(*args, **kwargs)
        return decorated
    return decorator


def requiere_empleado(f):
    """Decorador para rutas que SOLO pueden acceder empleados (no clientes)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not AUTH_ENABLED:
            return f(*args, **kwargs)

        try:
            verify_jwt_in_request()
            claims = get_jwt()
            
            if claims.get('es_cliente', True):
                return jsonify({
                    "success": False,
                    "error": "Acceso denegado",
                    "message": "Esta ruta solo es accesible para empleados del sistema"
                }), 403

        except Exception:
            return jsonify({
                "success": False,
                "error": "Token requerido o inválido",
                "message": "Debes iniciar sesión para acceder a este recurso"
            }), 401

        return f(*args, **kwargs)
    return decorated


def get_usuario_actual() -> dict:
    """Retorna el payload del JWT del usuario autenticado."""
    return get_jwt()