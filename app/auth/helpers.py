import logging
from werkzeug.security import check_password_hash
from flask_jwt_extended import create_access_token

security_logger = logging.getLogger('security')


def verificar_contrasenia(contrasenia_plana: str, contrasenia_guardada: str, usuario_id: int) -> bool:
    """Verifica contraseña"""
    print(f"🔐 Verificando contraseña para usuario_id={usuario_id}")
    print(f"   Largo hash guardado: {len(contrasenia_guardada)}")
    try:
        resultado = check_password_hash(contrasenia_guardada, contrasenia_plana)
        print(f"   ¿Coinciden? {resultado}")
        if resultado:
            security_logger.info(f"✅ Contraseña OK: usuario_id={usuario_id}")
        else:
            security_logger.warning(f"⚠️ Contraseña INCORRECTA: usuario_id={usuario_id}")
        return resultado
    except Exception as e:
        print(f"   ❌ Error en check_password_hash: {e}")
        security_logger.error(f"❌ Error: {e}")
        return False

def generar_token(usuario, permisos: list, nombre_rol: str, nombre_completo: str, es_cliente: bool, empleado_id: int = None) -> str:
    """Genera JWT con claims"""
    claims = {
        "id": usuario.id,
        "nombre": nombre_completo,
        "correo": usuario.correo,
        "rol": nombre_rol.lower() if nombre_rol else None,
        "rol_id": usuario.rol_id,
        "permisos": permisos,
        "es_cliente": es_cliente,
        "empleado_id": empleado_id,
        "cliente_id": usuario.cliente_id
    }
    return create_access_token(identity=str(usuario.id), additional_claims=claims)


def log_login_exitoso(usuario_id: int, nombre_rol: str, ip: str) -> None:
    security_logger.info(f"✅ Login OK | ID={usuario_id} | Rol={nombre_rol} | IP={ip}")


def log_login_fallido(motivo: str, correo: str, ip: str) -> None:
    security_logger.warning(f"⚠️ Login FAIL | Motivo={motivo} | Correo={correo} | IP={ip}")


def log_cuenta_inactiva(correo: str, ip: str) -> None:
    security_logger.warning(f"🚫 Login BLOCKED | Inactivo | Correo={correo} | IP={ip}")