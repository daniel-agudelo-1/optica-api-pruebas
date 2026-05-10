from flask import jsonify, request
from app.database import db
from app.Models.models import Usuario, Rol, Permiso, PermisoPorRol
from app.auth.decorators import permiso_requerido
import re
from datetime import datetime
from werkzeug.security import generate_password_hash
from app.routes import main_bp

EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
ROLES_CRITICOS = ['admin', 'superadmin']

# ===== USUARIOS =====
@main_bp.route('/usuarios', methods=['GET'])
@permiso_requerido('usuarios')
def get_usuarios():
    try:
        print("🔍 Intentando obtener usuarios...")
        usuarios = Usuario.query.all()
        print(f"✅ Encontrados {len(usuarios)} usuarios")
        usuarios_list = []
        for usuario in usuarios:
            try:
                usuario_dict = usuario.to_dict()
                usuarios_list.append(usuario_dict)
            except Exception as e:
                print(f"❌ Error convirtiendo usuario {usuario.id}: {e}")
                usuarios_list.append({'id': usuario.id, 'nombre': usuario.nombre, 'correo': usuario.correo, 'rol_id': usuario.rol_id, 'estado': usuario.estado})
        return jsonify(usuarios_list)
    except Exception as e:
        print(f"❌ ERROR CRÍTICO en get_usuarios: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error al obtener usuarios: {str(e)}"}), 500

@main_bp.route('/usuarios', methods=['POST'])
@permiso_requerido('usuarios')
def create_usuario():
    try:
        data = request.get_json()
        print(f"DEBUG DATA RECEIVIED: {data}")
        required_fields = ['nombre', 'correo', 'contrasenia', 'rol_id']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400
        if not EMAIL_REGEX.match(data['correo'].strip().lower()):
            return jsonify({"error": "Formato de correo inválido"}), 400
        if len(data['contrasenia']) < 6:
            return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400
        if Usuario.query.filter_by(correo=data['correo'].strip().lower()).first():
            return jsonify({"success": False, "error": "El correo ya está registrado"}), 400
        rol = Rol.query.get(data['rol_id'])
        if not rol:
            return jsonify({"error": "El rol especificado no existe"}), 400
        if not rol.estado:
            return jsonify({"error": "No puedes asignar un rol inactivo"}), 400
        contrasenia_hash = generate_password_hash(data['contrasenia'])
        cliente_id = None
        if data['rol_id'] == 2:
            nombre_parts = data['nombre'].split(' ')
            primer_nombre = nombre_parts[0]
            apellido = nombre_parts[1] if len(nombre_parts) > 1 else ''
            from app.Models.models import Cliente
            cliente = Cliente(
                nombre=primer_nombre,
                apellido=apellido,
                correo=data['correo'].strip().lower(),
                numero_documento=data.get('numero_documento', 'PENDIENTE'),
                fecha_nacimiento=data.get('fecha_nacimiento', datetime.now().date()),
                genero=data.get('genero'),
                telefono=data.get('telefono'),
                municipio=data.get('municipio'),
                direccion=data.get('direccion'),
                ocupacion=data.get('ocupacion'),
                telefono_emergencia=data.get('telefono_emergencia'),
                estado=True
            )
            db.session.add(cliente)
            db.session.flush()
            cliente_id = cliente.id
        usuario = Usuario(
            nombre=data['nombre'],
            correo=data['correo'].strip().lower(),
            contrasenia=contrasenia_hash,
            rol_id=data['rol_id'],
            estado=data.get('estado', True),
            cliente_id=cliente_id
        )
        db.session.add(usuario)
        db.session.commit()
        return jsonify({"success": True, "message": "Usuario creado exitosamente", "usuario": usuario.to_dict(), "cliente_id": cliente_id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Error al crear usuario: {str(e)}"}), 500

@main_bp.route('/usuarios/<int:id>', methods=['PUT'])
@permiso_requerido('usuarios')
def update_usuario(id):
    try:
        usuario = Usuario.query.get(id)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404
        data = request.get_json()
        if 'correo' in data:
            correo = data['correo'].strip().lower()
            if not EMAIL_REGEX.match(correo):
                return jsonify({"error": "Formato de correo inválido"}), 400
            existente = Usuario.query.filter_by(correo=correo).first()
            if existente and existente.id != id:
                return jsonify({"error": "El correo ya está registrado"}), 400
            usuario.correo = correo
        if 'nombre' in data:
            usuario.nombre = data['nombre']
        if 'contrasenia' in data:
            if len(data['contrasenia']) < 6:
                return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400
            usuario.contrasenia = generate_password_hash(data['contrasenia'])
        if 'rol_id' in data:
            rol = Rol.query.get(data['rol_id'])
            if not rol:
                return jsonify({"error": "El rol especificado no existe"}), 400
            if not rol.estado:
                return jsonify({"error": "No puedes asignar un rol inactivo"}), 400
            usuario.rol_id = data['rol_id']
        if 'estado' in data:
            usuario.estado = data['estado']
        db.session.commit()
        return jsonify({"message": "Usuario actualizado", "usuario": usuario.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar usuario"}), 500

@main_bp.route('/usuarios/<int:id>', methods=['DELETE'])
@permiso_requerido('usuarios')
def delete_usuario(id):
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
        return jsonify({"error": "Error al eliminar usuario"}), 500

# ===== ROLES =====
@main_bp.route('/roles', methods=['GET'])
@permiso_requerido('roles')
def get_roles():
    try:
        roles = Rol.query.all()
        return jsonify([rol.to_dict() for rol in roles])
    except Exception as e:
        return jsonify({"error": "Error al obtener roles"}), 500

@main_bp.route('/roles', methods=['POST'])
@permiso_requerido('roles')
def create_rol():
    try:
        data = request.get_json()
        if not data or not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400
        nombre = data['nombre'].strip()
        if len(nombre) < 3 or len(nombre) > 25:
            return jsonify({"error": "El nombre debe tener entre 3 y 25 caracteres"}), 400
        if nombre.lower() in ROLES_CRITICOS:
            return jsonify({"error": "No puedes crear un rol con ese nombre"}), 403
        if Rol.query.filter_by(nombre=nombre).first():
            return jsonify({"error": "Ya existe un rol con ese nombre"}), 400
        permisos_ids = data.get('permisos', [])
        permisos = []
        if permisos_ids:
            permisos = Permiso.query.filter(Permiso.id.in_(permisos_ids)).all()
            if len(permisos) != len(permisos_ids):
                return jsonify({"error": "Uno o más permisos no existen"}), 400
        estado_valor = data.get('estado', True)
        if isinstance(estado_valor, str):
            estado_bool = estado_valor == "activo"
        else:
            estado_bool = bool(estado_valor)
        rol = Rol(nombre=nombre, descripcion=data.get('descripcion', '').strip(), estado=estado_bool)
        rol.permisos = permisos
        db.session.add(rol)
        db.session.commit()
        return jsonify({"message": "Rol creado", "rol": rol.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear rol"}), 500

@main_bp.route('/roles/<int:id>', methods=['PUT'])
@permiso_requerido('roles')
def update_rol(id):
    try:
        rol = Rol.query.get(id)
        if not rol:
            return jsonify({"error": "Rol no encontrado"}), 404
        if rol.nombre.lower() in ROLES_CRITICOS:
            return jsonify({"error": "No puedes modificar este rol"}), 403
        data = request.get_json()
        if 'nombre' in data:
            nombre = data['nombre'].strip()
            if len(nombre) < 3 or len(nombre) > 25:
                return jsonify({"error": "El nombre debe tener entre 3 y 25 caracteres"}), 400
            existente = Rol.query.filter_by(nombre=nombre).first()
            if existente and existente.id != id:
                return jsonify({"error": "Ya existe un rol con ese nombre"}), 400
            rol.nombre = nombre
        if 'descripcion' in data:
            rol.descripcion = data['descripcion'].strip()
        if 'estado' in data:
            nuevo_estado = data['estado']
            if isinstance(nuevo_estado, str):
                nuevo_estado = nuevo_estado == "activo"
            if not nuevo_estado:
                usuarios_activos = Usuario.query.filter_by(rol_id=id, estado=True).count()
                if usuarios_activos > 0:
                    return jsonify({"error": f"No puedes desactivar este rol: tiene {usuarios_activos} usuario(s) activo(s)"}), 400
            rol.estado = nuevo_estado
        if 'permisos' in data:
            permisos_ids = data['permisos']
            permisos_ids = list(set(permisos_ids))
            if permisos_ids:
                permisos = Permiso.query.filter(Permiso.id.in_(permisos_ids)).all()
                if len(permisos) != len(permisos_ids):
                    return jsonify({"error": "Uno o más permisos no existen"}), 400
                rol.permisos = permisos
            else:
                rol.permisos = []
        db.session.commit()
        return jsonify({"message": "Rol actualizado", "rol": rol.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar rol"}), 500

@main_bp.route('/roles/<int:id>', methods=['DELETE'])
@permiso_requerido('roles')
def delete_rol(id):
    try:
        rol = Rol.query.get(id)
        if not rol:
            return jsonify({"error": "Rol no encontrado"}), 404
        if rol.nombre.lower() in ROLES_CRITICOS:
            return jsonify({"error": "No puedes eliminar este rol"}), 403
        if rol.estado:
            return jsonify({"error": "Debes desactivar el rol antes de eliminarlo"}), 400
        usuarios_count = Usuario.query.filter_by(rol_id=id).count()
        if usuarios_count > 0:
            return jsonify({"error": f"No puedes eliminar este rol: tiene {usuarios_count} usuario(s) asignado(s)"}), 400
        db.session.delete(rol)
        db.session.commit()
        return jsonify({"message": "Rol eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar rol"}), 500

# ===== PERMISOS =====
@main_bp.route('/permiso', methods=['GET'])
@permiso_requerido('configuracion')
def get_permisos():
    try:
        permisos = Permiso.query.all()
        return jsonify([permiso.to_dict() for permiso in permisos])
    except Exception as e:
        return jsonify({"error": "Error al obtener permisos"}), 500

@main_bp.route('/permiso', methods=['POST'])
@permiso_requerido('configuracion')
def create_permiso():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400
        permiso = Permiso(nombre=data['nombre'])
        db.session.add(permiso)
        db.session.commit()
        return jsonify({"message": "Permiso creado", "permiso": permiso.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear permiso"}), 500

@main_bp.route('/permiso/<int:id>', methods=['PUT'])
@permiso_requerido('configuracion')
def update_permiso(id):
    try:
        permiso = Permiso.query.get(id)
        if not permiso:
            return jsonify({"error": "Permiso no encontrado"}), 404
        data = request.get_json()
        if 'nombre' in data:
            permiso.nombre = data['nombre']
        db.session.commit()
        return jsonify({"message": "Permiso actualizado", "permiso": permiso.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar permiso"}), 500

@main_bp.route('/permiso/<int:id>', methods=['DELETE'])
@permiso_requerido('configuracion')
def delete_permiso(id):
    try:
        permiso = Permiso.query.get(id)
        if not permiso:
            return jsonify({"error": "Permiso no encontrado"}), 404
        db.session.delete(permiso)
        db.session.commit()
        return jsonify({"message": "Permiso eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar permiso"}), 500

@main_bp.route('/permiso-rol', methods=['GET'])
@permiso_requerido('configuracion')
def get_permisos_rol():
    try:
        permisos_rol = PermisoPorRol.query.all()
        return jsonify([permiso.to_dict() for permiso in permisos_rol])
    except Exception as e:
        return jsonify({"error": "Error al obtener permisos por rol"}), 500

@main_bp.route('/permiso-rol', methods=['POST'])
@permiso_requerido('configuracion')
def create_permiso_rol():
    try:
        data = request.get_json()
        required_fields = ['rol_id', 'permiso_id']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400
        permiso_rol = PermisoPorRol(rol_id=data['rol_id'], permiso_id=data['permiso_id'])
        db.session.add(permiso_rol)
        db.session.commit()
        return jsonify({"message": "Permiso por rol creado", "permiso_rol": permiso_rol.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear permiso por rol"}), 500

@main_bp.route('/permiso-rol/<int:id>', methods=['PUT'])
@permiso_requerido('configuracion')
def update_permiso_rol(id):
    try:
        permiso_rol = PermisoPorRol.query.get(id)
        if not permiso_rol:
            return jsonify({"error": "Permiso por rol no encontrado"}), 404
        data = request.get_json()
        if 'rol_id' in data:
            permiso_rol.rol_id = data['rol_id']
        if 'permiso_id' in data:
            permiso_rol.permiso_id = data['permiso_id']
        db.session.commit()
        return jsonify({"message": "Permiso por rol actualizado", "permiso_rol": permiso_rol.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar permiso por rol"}), 500

@main_bp.route('/permiso-rol/<int:id>', methods=['DELETE'])
@permiso_requerido('configuracion')
def delete_permiso_rol(id):
    try:
        permiso_rol = PermisoPorRol.query.get(id)
        if not permiso_rol:
            return jsonify({"error": "Permiso por rol no encontrado"}), 404
        db.session.delete(permiso_rol)
        db.session.commit()
        return jsonify({"message": "Permiso por rol eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar permiso por rol"}), 500