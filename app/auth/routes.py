"""
Blueprint de autenticación: /auth

Rutas:
    POST /auth/login            → login con JWT
    POST /auth/register         → inicia registro, envía código por Brevo
    POST /auth/verify-register  → verifica código y crea el cliente + usuario (con rol Cliente)
    POST /auth/forgot-password  → envía código de recuperación por Brevo (solo para usuarios con rol)
    POST /auth/reset-password   → verifica código y actualiza contraseña
    POST /auth/logout           → cierra sesión (instrucción al frontend)
    GET  /auth/me               → retorna datos del usuario autenticado
"""

import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from app.database import db
from app.Models.models import Usuario, Cliente, Empleado, Rol
from app.services.email_service import enviar_codigo_verificacion, enviar_codigo_reset
from .helpers import (
    verificar_contrasenia,
    generar_token,
    log_login_exitoso,
    log_login_fallido,
    log_cuenta_inactiva,
)
from .decorators import get_usuario_actual, jwt_requerido

auth_bp = Blueprint('auth', __name__)

EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

# Almacenamiento temporal de códigos en memoria RAM.
codigos_verificacion: dict = {}
codigos_reset: dict = {}

EXPIRACION_MINUTOS = 15


def _codigo_expirado(registro: dict) -> bool:
    return datetime.utcnow() > registro.get("expira", datetime.utcnow())


def _obtener_rol_cliente():
    """Retorna el objeto Rol correspondiente a 'Cliente' o None si no existe."""
    return Rol.query.filter_by(nombre='Cliente').first()


# =============================================
# POST /auth/login
# =============================================
@auth_bp.route('/login', methods=['POST'])
def login():
    ip_cliente = request.remote_addr

    try:
        data = request.get_json(silent=True)

        if not data or not data.get('correo') or not data.get('contrasenia'):
            return jsonify({
                "success": False,
                "code": "MISSING_FIELDS",
                "error": "Campos requeridos",
                "message": "Correo y contraseña son obligatorios."
            }), 400

        correo = data['correo'].strip().lower()
        contrasenia = data['contrasenia']

        if not EMAIL_REGEX.match(correo):
            return jsonify({
                "success": False,
                "code": "INVALID_EMAIL",
                "error": "Correo inválido",
                "message": "El formato del correo electrónico no es válido."
            }), 400

        if len(contrasenia.strip()) < 6:
            return jsonify({
                "success": False,
                "code": "WEAK_PASSWORD",
                "error": "Contraseña muy corta",
                "message": "La contraseña debe tener al menos 6 caracteres."
            }), 400

        usuario = Usuario.query.filter_by(correo=correo).first()

        # Logs internos para depuración
        print(f"🔍 Login intento: correo={correo}")
        if usuario:
            print(f"   Usuario ID={usuario.id}, rol_id={usuario.rol_id}, estado={usuario.estado}")
            print(f"   Hash de contraseña (primeros 20): {usuario.contrasenia[:20]}...")
        else:
            print("   Usuario NO encontrado")

        if not usuario:
            log_login_fallido("correo no existe", correo, ip_cliente)
            return jsonify({
                "success": False,
                "code": "INVALID_CREDENTIALS",
                "error": "Credenciales incorrectas",
                "message": "El correo o la contraseña no son correctos. Si no recuerdas tu contraseña, utiliza '¿Olvidaste tu contraseña?'."
            }), 401

        if not usuario.estado:
            log_cuenta_inactiva(correo, ip_cliente)
            return jsonify({
                "success": False,
                "code": "ACCOUNT_INACTIVE",
                "error": "Cuenta inactiva",
                "message": "Tu cuenta ha sido desactivada. Contacta al administrador para más información."
            }), 403

        # Verificar contraseña
        contrasenia_valida = verificar_contrasenia(
            contrasenia,
            usuario.contrasenia,
            usuario.id
        )
        if not contrasenia_valida:
            log_login_fallido("contraseña incorrecta", correo, ip_cliente)
            return jsonify({
                "success": False,
                "code": "INVALID_CREDENTIALS",
                "error": "Credenciales incorrectas",
                "message": "La contraseña es incorrecta. Puedes restablecerla desde '¿Olvidaste tu contraseña?'."
            }), 401

        # ============================================================
        # NUEVA LÓGICA UNIFICADA (SIN empleado_id)
        # ============================================================
        nombre_completo = f"{usuario.nombre or ''} {usuario.apellido or ''}".strip()
        if not nombre_completo:
            nombre_completo = usuario.correo

        permisos = []
        rol_nombre = None
        if usuario.rol:
            rol_nombre = usuario.rol.nombre
            permisos = [p.nombre for p in usuario.rol.permisos] if usuario.rol.permisos else []

        # Determinar si es cliente (por nombre de rol)
        es_cliente = (rol_nombre == 'Cliente')

        token = generar_token(
            usuario=usuario,
            permisos=permisos,
            nombre_rol=rol_nombre,
            nombre_completo=nombre_completo,
            es_cliente=es_cliente,
            empleado_id=None   # Ya no se usa, pero se mantiene por compatibilidad
        )
        log_login_exitoso(usuario.id, rol_nombre or "cliente", ip_cliente)

        return jsonify({
            "success": True,
            "token": token,
            "usuario": {
                "id": usuario.id,
                "nombre": nombre_completo,
                "correo": usuario.correo,
                "rol": rol_nombre,
                "rol_id": usuario.rol_id,
                "permisos": permisos,
                "es_cliente": es_cliente
                # empleado_id omitido
            }
        }), 200

    except Exception as e:
        # En producción, registrar el error en un log
        print(f"❌ Error en login: {str(e)}")
        return jsonify({
            "success": False,
            "code": "SERVER_ERROR",
            "error": "Error interno",
            "message": "Ocurrió un error inesperado. Intenta de nuevo más tarde."
        }), 500


# =============================================
# POST /auth/register - Registro de CLIENTE
# =============================================
@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "success": False,
                "code": "INVALID_REQUEST",
                "error": "Cuerpo inválido",
                "message": "La solicitud no contiene datos válidos."
            }), 400

        required_fields = ['nombre', 'apellido', 'correo', 'contrasenia', 'numeroDocumento', 'fechaNacimiento']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    "success": False,
                    "code": "MISSING_FIELD",
                    "error": f"Falta el campo '{field}'",
                    "message": f"El campo '{field}' es obligatorio."
                }), 400

        correo = data['correo'].strip().lower()
        nombre = data['nombre'].strip()
        apellido = data['apellido'].strip()

        if not EMAIL_REGEX.match(correo):
            return jsonify({
                "success": False,
                "code": "INVALID_EMAIL",
                "error": "Correo inválido",
                "message": "El formato del correo electrónico no es válido."
            }), 400

        if len(data['contrasenia']) < 6:
            return jsonify({
                "success": False,
                "code": "WEAK_PASSWORD",
                "error": "Contraseña muy corta",
                "message": "La contraseña debe tener al menos 6 caracteres."
            }), 400

        if Usuario.query.filter_by(correo=correo).first():
            return jsonify({
                "success": False,
                "code": "EMAIL_ALREADY_REGISTERED",
                "error": "Correo duplicado",
                "message": "Ya existe una cuenta con este correo. Inicia sesión o recupera tu contraseña."
            }), 400

        codigo = str(secrets.randbelow(900000) + 100000)
        codigos_verificacion[correo] = {
            "codigo": codigo,
            "data": data,
            "expira": datetime.utcnow() + timedelta(minutes=EXPIRACION_MINUTOS)
        }

        enviado = enviar_codigo_verificacion(
            correo=correo,
            nombre=f"{nombre} {apellido}",
            codigo=codigo
        )

        if not enviado:
            del codigos_verificacion[correo]
            return jsonify({
                "success": False,
                "code": "EMAIL_SEND_FAILED",
                "error": "Error al enviar código",
                "message": "No se pudo enviar el código de verificación. Verifica el correo e intenta de nuevo."
            }), 500

        return jsonify({
            "success": True,
            "code": "CODE_SENT",
            "message": "Código de verificación enviado al correo electrónico."
        }), 200

    except Exception as e:
        print(f"❌ Error en register: {str(e)}")
        return jsonify({
            "success": False,
            "code": "SERVER_ERROR",
            "error": "Error interno",
            "message": "No se pudo procesar el registro. Intenta de nuevo más tarde."
        }), 500


# =============================================
# POST /auth/verify-register - CREA CLIENTE + USUARIO (CON ROL CLIENTE)
# =============================================
@auth_bp.route('/verify-register', methods=['POST'])
def verify_register():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "success": False,
                "code": "INVALID_REQUEST",
                "error": "Cuerpo inválido",
                "message": "La solicitud no contiene datos válidos."
            }), 400

        correo = data.get('correo', '').strip().lower()
        codigo = data.get('codigo', '').strip()

        if not correo or not codigo:
            return jsonify({
                "success": False,
                "code": "MISSING_FIELDS",
                "error": "Faltan campos",
                "message": "Correo y código son requeridos."
            }), 400

        if correo not in codigos_verificacion:
            return jsonify({
                "success": False,
                "code": "NO_PENDING_REGISTRATION",
                "error": "Registro no iniciado",
                "message": "No hay una solicitud de registro pendiente para este correo. Inicia el proceso desde el formulario de registro."
            }), 400

        registro = codigos_verificacion[correo]

        if _codigo_expirado(registro):
            del codigos_verificacion[correo]
            return jsonify({
                "success": False,
                "code": "CODE_EXPIRED",
                "error": "Código expirado",
                "message": "El código ha expirado. Solicita uno nuevo desde el registro."
            }), 400

        if registro['codigo'] != codigo:
            return jsonify({
                "success": False,
                "code": "INVALID_CODE",
                "error": "Código incorrecto",
                "message": "El código ingresado no es correcto. Verifica e intenta de nuevo."
            }), 400

        form_data = registro['data']

        from werkzeug.security import generate_password_hash

        # ============================================================
        # 1. CREAR CLIENTE
        # ============================================================
        cliente = Cliente(
            nombre=form_data['nombre'].strip(),
            apellido=form_data['apellido'].strip(),
            correo=correo,
            numero_documento=str(form_data['numeroDocumento']).strip(),
            tipo_documento=form_data.get('tipoDocumento', 'CC'),
            fecha_nacimiento=datetime.strptime(form_data['fechaNacimiento'], '%Y-%m-%d').date(),
            telefono=form_data.get('telefono', ''),
            genero=form_data.get('genero', ''),
            direccion=form_data.get('direccion', ''),
            departamento=form_data.get('departamento', ''),
            municipio=form_data.get('municipio', ''),
            barrio=form_data.get('barrio', ''),
            codigo_postal=form_data.get('codigoPostal', ''),
            ocupacion=form_data.get('ocupacion', ''),
            telefono_emergencia=form_data.get('telefonoEmergencia', ''),
            estado=True
        )
        db.session.add(cliente)
        db.session.flush()  # Para obtener el ID del cliente

        # ============================================================
        # 2. CREAR USUARIO CON ROL "Cliente"
        # ============================================================
        rol_cliente = _obtener_rol_cliente()
        if not rol_cliente:
            # Por seguridad, creamos el rol Cliente si no existe
            rol_cliente = Rol(nombre='Cliente', descripcion='Rol para clientes registrados', estado=True)
            db.session.add(rol_cliente)
            db.session.flush()

        usuario = Usuario(
            correo=correo,
            contrasenia=generate_password_hash(form_data['contrasenia']),
            rol_id=rol_cliente.id,
            estado=True,
            cliente_id=cliente.id
        )
        # Guardar datos personales directamente en usuario
        usuario.nombre = form_data['nombre'].strip()
        usuario.apellido = form_data['apellido'].strip()
        usuario.telefono = form_data.get('telefono', '')
        usuario.tipo_documento = form_data.get('tipoDocumento', 'CC')
        usuario.numero_documento = str(form_data['numeroDocumento']).strip()
        try:
            usuario.fecha_nacimiento = datetime.strptime(form_data['fechaNacimiento'], '%Y-%m-%d').date()
        except:
            usuario.fecha_nacimiento = None

        db.session.add(usuario)
        db.session.commit()

        # Limpiar código
        del codigos_verificacion[correo]

        # ============================================================
        # 3. GENERAR JWT PARA EL CLIENTE
        # ============================================================
        nombre_completo = f"{cliente.nombre} {cliente.apellido}"
        token = generar_token(
            usuario=usuario,
            permisos=[],   # El rol Cliente no tiene permisos por defecto
            nombre_rol='Cliente',
            nombre_completo=nombre_completo,
            es_cliente=True,
            empleado_id=None
        )

        return jsonify({
            "success": True,
            "code": "REGISTRATION_COMPLETE",
            "message": "Cliente registrado exitosamente.",
            "token": token,
            "usuario": {
                "id": usuario.id,
                "nombre": nombre_completo,
                "correo": usuario.correo,
                "rol": "Cliente",
                "rol_id": usuario.rol_id,
                "permisos": [],
                "es_cliente": True,
                "cliente_id": cliente.id
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error en verify_register: {str(e)}")
        return jsonify({
            "success": False,
            "code": "SERVER_ERROR",
            "error": "Error interno",
            "message": "No se pudo completar el registro. Intenta de nuevo más tarde."
        }), 500


# =============================================
# POST /auth/forgot-password (solo para usuarios con rol, no clientes)
# =============================================
@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json(silent=True)
        correo = (data.get('correo', '') if data else '').strip().lower()

        if not correo or not EMAIL_REGEX.match(correo):
            return jsonify({
                "success": False,
                "code": "INVALID_EMAIL",
                "error": "Correo inválido",
                "message": "El formato del correo electrónico no es válido."
            }), 400

        usuario = Usuario.query.filter_by(correo=correo).first()
        RESPUESTA_GENERICA = {
            "success": True,
            "code": "RESET_SENT_IF_EXISTS",
            "message": "Si el correo existe y tiene permisos para recuperar contraseña, recibirás un código en los próximos minutos. Revisa también tu carpeta de spam."
        }

        if not usuario:
            return jsonify(RESPUESTA_GENERICA), 200

        # Solo permitir recuperación a usuarios que tienen rol (administrativos)
        if usuario.rol_id is None:
            return jsonify(RESPUESTA_GENERICA), 200

        # Generar código
        codigo = str(secrets.randbelow(900000) + 100000)
        codigos_reset[correo] = {
            "codigo": codigo,
            "usuario_id": usuario.id,
            "expira": datetime.utcnow() + timedelta(minutes=EXPIRACION_MINUTOS)
        }

        # Obtener nombre completo desde los campos directos
        nombre_completo = f"{usuario.nombre or ''} {usuario.apellido or ''}".strip()
        if not nombre_completo:
            nombre_completo = usuario.correo

        enviado = enviar_codigo_reset(
            correo=correo,
            nombre=nombre_completo,
            codigo=codigo
        )

        if not enviado:
            del codigos_reset[correo]
            # No revelamos el fallo al usuario para mantener seguridad
            return jsonify(RESPUESTA_GENERICA), 200

        return jsonify(RESPUESTA_GENERICA), 200

    except Exception as e:
        print(f"❌ Error en forgot_password: {str(e)}")
        return jsonify({
            "success": False,
            "code": "SERVER_ERROR",
            "error": "Error interno",
            "message": "No se pudo procesar la solicitud. Intenta de nuevo más tarde."
        }), 500


# =============================================
# POST /auth/reset-password
# =============================================
@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({
                "success": False,
                "code": "INVALID_REQUEST",
                "error": "Cuerpo inválido",
                "message": "La solicitud no contiene datos válidos."
            }), 400

        correo = data.get('correo', '').strip().lower()
        codigo = data.get('codigo', '').strip()
        nueva_contrasenia = data.get('nueva_contrasenia', '')

        if not all([correo, codigo, nueva_contrasenia]):
            return jsonify({
                "success": False,
                "code": "MISSING_FIELDS",
                "error": "Faltan campos",
                "message": "Correo, código y nueva contraseña son requeridos."
            }), 400

        if len(nueva_contrasenia) < 6:
            return jsonify({
                "success": False,
                "code": "WEAK_PASSWORD",
                "error": "Contraseña muy corta",
                "message": "La nueva contraseña debe tener al menos 6 caracteres."
            }), 400

        if correo not in codigos_reset:
            return jsonify({
                "success": False,
                "code": "NO_RESET_REQUEST",
                "error": "Solicitud no encontrada",
                "message": "No hay una solicitud de recuperación activa para este correo. Solicita un nuevo código."
            }), 400

        reset = codigos_reset[correo]

        if _codigo_expirado(reset):
            del codigos_reset[correo]
            return jsonify({
                "success": False,
                "code": "CODE_EXPIRED",
                "error": "Código expirado",
                "message": "El código ha caducado. Solicita uno nuevo desde 'olvidé mi contraseña'."
            }), 400

        if reset['codigo'] != codigo:
            return jsonify({
                "success": False,
                "code": "INVALID_CODE",
                "error": "Código incorrecto",
                "message": "El código ingresado no es correcto. Verifica e intenta de nuevo."
            }), 400

        from werkzeug.security import generate_password_hash
        usuario = Usuario.query.get(reset['usuario_id'])
        if not usuario:
            return jsonify({
                "success": False,
                "code": "USER_NOT_FOUND",
                "error": "Usuario no encontrado",
                "message": "El usuario asociado a esta solicitud ya no existe."
            }), 404

        usuario.contrasenia = generate_password_hash(nueva_contrasenia)
        db.session.commit()

        del codigos_reset[correo]

        return jsonify({
            "success": True,
            "code": "PASSWORD_RESET",
            "message": "Contraseña actualizada correctamente. Ya puedes iniciar sesión."
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error en reset_password: {str(e)}")
        return jsonify({
            "success": False,
            "code": "SERVER_ERROR",
            "error": "Error interno",
            "message": "No se pudo actualizar la contraseña. Intenta de nuevo más tarde."
        }), 500


# =============================================
# POST /auth/logout
# =============================================
@auth_bp.route('/logout', methods=['POST'])
def logout():
    return jsonify({
        "success": True,
        "code": "LOGOUT_SUCCESS",
        "message": "Sesión cerrada correctamente"
    }), 200


# =============================================
# GET /auth/me
# =============================================
@auth_bp.route('/me', methods=['GET'])
@jwt_requerido
def me():
    claims = get_usuario_actual()
    return jsonify({
        "success": True,
        "usuario": {
            "id": claims.get("id"),
            "nombre": claims.get("nombre"),
            "correo": claims.get("correo"),
            "rol": claims.get("rol"),
            "rol_id": claims.get("rol_id"),
            "permisos": claims.get("permisos", []),
            "es_cliente": claims.get("es_cliente", False),
            "cliente_id": claims.get("cliente_id") 
        }
    }), 200