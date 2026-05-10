from flask import jsonify, request
from app.database import db
from app.Models.models import Usuario, Rol
from app.auth.decorators import permiso_requerido, get_usuario_actual
from werkzeug.security import generate_password_hash, check_password_hash
from app.routes import main_bp
import re

EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PASSWORD_REGEX = re.compile(r'^(?=.*[A-Z])(?=.*\d).{6,}$')


# ============================================================
# PERFIL PROPIO — cualquier usuario autenticado
# ============================================================

@main_bp.route('/usuario/perfil', methods=['GET'])
def get_mi_perfil_usuario():
    try:
        claims = get_usuario_actual()
        usuario = Usuario.query.get(claims.get('id'))
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        return jsonify({
            "id": usuario.id,
            "correo": usuario.correo,
            "rol_id": usuario.rol_id,
            "rol_nombre": usuario.rol.nombre if usuario.rol else None,
            "permisos": claims.get('permisos', []),
            "estado": usuario.estado,
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "telefono": usuario.telefono,
            "tipo_documento": usuario.tipo_documento,
            "numero_documento": usuario.numero_documento,
            "fecha_nacimiento": usuario.fecha_nacimiento.isoformat() if usuario.fecha_nacimiento else None,
            "cliente": usuario.cliente.to_dict() if usuario.cliente else None
        })
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500


@main_bp.route('/usuario/cambiar-contrasenia', methods=['POST'])
def cambiar_mi_contrasenia_usuario():
    try:
        claims = get_usuario_actual()
        usuario = Usuario.query.get(claims.get('id'))
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        data = request.get_json()

        if not check_password_hash(usuario.contrasenia, data.get('contrasenia_actual', '')):
            return jsonify({"error": "Contraseña actual incorrecta"}), 401

        nueva = data.get('nueva_contrasenia', '')
        if not PASSWORD_REGEX.match(nueva):
            return jsonify({"error": "La nueva contraseña debe tener al menos 6 caracteres, una mayúscula y un número"}), 400

        usuario.contrasenia = generate_password_hash(nueva)
        db.session.commit()
        return jsonify({"success": True, "message": "Contraseña actualizada"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error: {str(e)}"}), 500


# ============================================================
# ADMINISTRACIÓN — SOLO usuarios administrativos (con rol)
# ============================================================

@main_bp.route('/admin/usuarios', methods=['GET'])
@permiso_requerido("usuarios")
def get_usuarios_admin():
    """Listar SOLO usuarios administrativos (con rol, excluyendo clientes)"""
    try:
        usuarios = Usuario.query.filter(Usuario.rol_id.isnot(None)).all()
        return jsonify([u.to_dict() for u in usuarios])
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500


@main_bp.route('/admin/usuarios', methods=['POST'])
@permiso_requerido("usuarios")
def create_usuario_admin():
    """
    Crea un usuario administrativo.
    REQUIERE: nombre, correo, contrasenia, rol_id
    """
    try:
        data = request.get_json()

        required_fields = ['nombre', 'correo', 'contrasenia', 'rol_id']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"El campo '{field}' es requerido"}), 400

        correo = data['correo'].strip().lower()
        if not EMAIL_REGEX.match(correo):
            return jsonify({"error": "Formato de correo inválido"}), 400

        contrasenia = data['contrasenia']
        if not PASSWORD_REGEX.match(contrasenia):
            return jsonify({"error": "La contraseña debe tener al menos 6 caracteres, una mayúscula y un número"}), 400

        if Usuario.query.filter_by(correo=correo).first():
            return jsonify({"error": "El correo ya está registrado"}), 400

        rol = Rol.query.get(data['rol_id'])
        if not rol:
            return jsonify({"error": "El rol especificado no existe"}), 400

        usuario = Usuario(
            nombre=data['nombre'].strip(),
            correo=correo,
            contrasenia=generate_password_hash(contrasenia),
            rol_id=rol.id,
            cliente_id=None,
            estado=data.get('estado', True)
        )

        db.session.add(usuario)
        db.session.commit()

        return jsonify({"success": True, "message": "Usuario creado", "usuario": usuario.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error: {str(e)}"}), 500


@main_bp.route('/admin/usuarios/<int:id>', methods=['GET'])
@permiso_requerido("usuarios")
def get_usuario(id):
    try:
        usuario = Usuario.query.get(id)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404
        return jsonify(usuario.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500


@main_bp.route('/admin/usuarios/<int:id>', methods=['PUT'])
@permiso_requerido("usuarios")
def update_usuario_admin(id):
    try:
        usuario = Usuario.query.get(id)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        data = request.get_json()

        # Actualizar nombre
        if 'nombre' in data:
            usuario.nombre = data['nombre'].strip()

        # Actualizar correo
        if 'correo' in data:
            correo = data['correo'].strip().lower()
            if not EMAIL_REGEX.match(correo):
                return jsonify({"error": "Formato de correo inválido"}), 400
            existente = Usuario.query.filter_by(correo=correo).first()
            if existente and existente.id != id:
                return jsonify({"error": "El correo ya está registrado"}), 400
            usuario.correo = correo

        # Actualizar contraseña (solo si se envía y no está vacía)
        if 'contrasenia' in data and data['contrasenia']:
            if not PASSWORD_REGEX.match(data['contrasenia']):
                return jsonify({"error": "La contraseña debe tener al menos 6 caracteres, una mayúscula y un número"}), 400
            usuario.contrasenia = generate_password_hash(data['contrasenia'])

        # Actualizar rol
        if 'rol_id' in data:
            rol = Rol.query.get(data['rol_id'])
            if not rol:
                return jsonify({"error": "El rol especificado no existe"}), 400
            usuario.rol_id = data['rol_id']

        # Actualizar estado
        if 'estado' in data:
            usuario.estado = data['estado']

        db.session.commit()
        return jsonify({"success": True, "message": "Usuario actualizado", "usuario": usuario.to_dict()})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error: {str(e)}"}), 500


@main_bp.route('/admin/usuarios/<int:id>', methods=['DELETE'])
@permiso_requerido("usuarios")
def delete_usuario_admin(id):
    try:
        usuario = Usuario.query.get(id)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        if usuario.estado:
            return jsonify({"error": "Debes desactivar el usuario antes de eliminarlo"}), 400

        db.session.delete(usuario)
        db.session.commit()
        return jsonify({"message": "Usuario eliminado correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error: {str(e)}"}), 500