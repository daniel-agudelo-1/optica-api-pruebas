from flask import jsonify, request
from app.database import db
from app.Models.models import Cliente, HistorialFormula, Cita, Usuario, Empleado, Servicio, EstadoCita
from app.auth.decorators import permiso_requerido
from datetime import datetime
from app.routes import main_bp
import re
from app.auth.decorators import jwt_requerido, get_usuario_actual

EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PHONE_REGEX = re.compile(r'^\d{7,15}$')

# ============================================================
# NOTA IMPORTANTE:
# Los clientes se registran desde landing y obtienen un usuario
# con rol_id = NULL (sin rol administrativo)
# ============================================================

# ============================================================
# RUTAS PÚBLICAS (Landing page) — SIN autenticación
# ============================================================

@main_bp.route('/clientes', methods=['GET'])
def get_clientes_publico():
    """Listar clientes (público)"""
    try:
        clientes = Cliente.query.all()
        return jsonify([cliente.to_dict() for cliente in clientes])
    except Exception as e:
        return jsonify({"error": f"Error al obtener clientes: {str(e)}"}), 500


@main_bp.route('/clientes', methods=['POST'])
def create_cliente_publico():
    """
    Registro de cliente desde landing page.
    NOTA: Este endpoint es solo para crear clientes.
    El registro completo (cliente + usuario) se hace en /auth/verify-register
    """
    try:
        data = request.get_json()

        required_fields = ['nombre', 'apellido', 'numero_documento', 'fecha_nacimiento']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        nombre = data['nombre'].strip()
        apellido = data['apellido'].strip()
        numero_documento = str(data['numero_documento']).strip()

        if not nombre or not apellido:
            return jsonify({"error": "Nombre y apellido son requeridos"}), 400

        if Cliente.query.filter_by(numero_documento=numero_documento).first():
            return jsonify({"error": "Ya existe un cliente con este número de documento"}), 400

        try:
            fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
            if fecha_nacimiento > datetime.now().date():
                return jsonify({"error": "La fecha de nacimiento no puede ser futura"}), 400
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400

        correo = data.get('correo', '').strip() or None
        if correo and not EMAIL_REGEX.match(correo):
            return jsonify({"error": "Formato de correo electrónico inválido"}), 400

        telefono = data.get('telefono', '').strip() or None
        if telefono and not PHONE_REGEX.match(telefono):
            return jsonify({"error": "El teléfono debe contener solo números (7-15 dígitos)"}), 400

        cliente = Cliente(
            nombre=nombre,
            apellido=apellido,
            tipo_documento=data.get('tipo_documento', '').strip() or None,
            numero_documento=numero_documento,
            fecha_nacimiento=fecha_nacimiento,
            genero=data.get('genero', '').strip() or None,
            telefono=telefono,
            correo=correo,
            municipio=data.get('municipio', '').strip() or None,
            direccion=data.get('direccion', '').strip() or None,
            departamento=data.get('departamento', '').strip() or None,
            barrio=data.get('barrio', '').strip() or None,
            codigo_postal=data.get('codigo_postal', '').strip() or None,
            ocupacion=data.get('ocupacion', '').strip() or None,
            telefono_emergencia=data.get('telefono_emergencia', '').strip() or None,
            estado=data.get('estado', True)
        )

        db.session.add(cliente)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Cliente creado exitosamente",
            "cliente": cliente.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear cliente: {str(e)}"}), 500


@main_bp.route('/clientes/<int:id>', methods=['PUT'])
def update_cliente_publico(id):
    """Actualizar cliente desde landing (público)"""
    try:
        cliente = Cliente.query.get(id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        data = request.get_json()

        if 'nombre' in data:
            cliente.nombre = data['nombre'].strip()
        if 'apellido' in data:
            cliente.apellido = data['apellido'].strip()
        if 'tipo_documento' in data:
            cliente.tipo_documento = data['tipo_documento'].strip() or None
        if 'numero_documento' in data:
            doc = str(data['numero_documento']).strip()
            existente = Cliente.query.filter_by(numero_documento=doc).first()
            if existente and existente.id != id:
                return jsonify({"error": "Ya existe otro cliente con este número de documento"}), 400
            cliente.numero_documento = doc
        if 'fecha_nacimiento' in data:
            try:
                cliente.fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
        if 'genero' in data:
            cliente.genero = data['genero'].strip() or None
        if 'telefono' in data:
            telefono = data['telefono'].strip() if data['telefono'] else None
            if telefono and not PHONE_REGEX.match(telefono):
                return jsonify({"error": "El teléfono debe contener solo números (7-15 dígitos)"}), 400
            cliente.telefono = telefono
        if 'correo' in data:
            correo = data['correo'].strip() if data['correo'] else None
            if correo and not EMAIL_REGEX.match(correo):
                return jsonify({"error": "Formato de correo electrónico inválido"}), 400
            cliente.correo = correo
        if 'municipio' in data:
            cliente.municipio = data['municipio'].strip() or None
        if 'direccion' in data:
            cliente.direccion = data['direccion'].strip() or None
        if 'departamento' in data:
            cliente.departamento = data['departamento'].strip() or None
        if 'barrio' in data:
            cliente.barrio = data['barrio'].strip() or None
        if 'codigo_postal' in data:
            cliente.codigo_postal = data['codigo_postal'].strip() or None
        if 'ocupacion' in data:
            cliente.ocupacion = data['ocupacion'].strip() or None
        if 'telefono_emergencia' in data:
            cliente.telefono_emergencia = data['telefono_emergencia'].strip() or None

        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Cliente actualizado",
            "cliente": cliente.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@main_bp.route('/clientes/<int:id>', methods=['DELETE'])
def delete_cliente_publico(id):
    """Eliminar cliente (solo si no tiene asociaciones)"""
    try:
        cliente = Cliente.query.get(id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        if cliente.citas and len(cliente.citas) > 0:
            return jsonify({"error": "No se puede eliminar: tiene citas asociadas"}), 400
        if cliente.ventas and len(cliente.ventas) > 0:
            return jsonify({"error": "No se puede eliminar: tiene ventas asociadas"}), 400
        if cliente.pedidos and len(cliente.pedidos) > 0:
            return jsonify({"error": "No se puede eliminar: tiene pedidos asociados"}), 400

        db.session.delete(cliente)
        db.session.commit()
        return jsonify({"message": "Cliente eliminado correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar cliente: {str(e)}"}), 500


# ============================================================
# ADMINISTRACIÓN DE CLIENTES — requiere permiso 'clientes'
# ============================================================

@main_bp.route('/admin/clientes', methods=['GET'])
@permiso_requerido('clientes')
def get_clientes():
    try:
        clientes = Cliente.query.all()
        return jsonify([cliente.to_dict() for cliente in clientes])
    except Exception as e:
        return jsonify({"error": f"Error al obtener clientes: {str(e)}"}), 500


@main_bp.route('/admin/clientes', methods=['POST'])
@permiso_requerido('clientes')
def create_cliente():
    try:
        data = request.get_json()

        required_fields = ['nombre', 'apellido', 'numero_documento', 'fecha_nacimiento']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        nombre = data['nombre'].strip()
        apellido = data['apellido'].strip()
        numero_documento = str(data['numero_documento']).strip()

        if not nombre or not apellido:
            return jsonify({"error": "Nombre y apellido son requeridos"}), 400

        if Cliente.query.filter_by(numero_documento=numero_documento).first():
            return jsonify({"error": "Ya existe un cliente con este número de documento"}), 400

        try:
            fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
            if fecha_nacimiento > datetime.now().date():
                return jsonify({"error": "La fecha de nacimiento no puede ser futura"}), 400
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400

        correo = data.get('correo', '').strip() or None
        if correo and not EMAIL_REGEX.match(correo):
            return jsonify({"error": "Formato de correo electrónico inválido"}), 400

        telefono = data.get('telefono', '').strip() or None
        if telefono and not PHONE_REGEX.match(telefono):
            return jsonify({"error": "El teléfono debe contener solo números (7-15 dígitos)"}), 400

        cliente = Cliente(
            nombre=nombre,
            apellido=apellido,
            tipo_documento=data.get('tipo_documento', '').strip() or None,
            numero_documento=numero_documento,
            fecha_nacimiento=fecha_nacimiento,
            genero=data.get('genero', '').strip() or None,
            telefono=telefono,
            correo=correo,
            municipio=data.get('municipio', '').strip() or None,
            direccion=data.get('direccion', '').strip() or None,
            departamento=data.get('departamento', '').strip() or None,
            barrio=data.get('barrio', '').strip() or None,
            codigo_postal=data.get('codigo_postal', '').strip() or None,
            ocupacion=data.get('ocupacion', '').strip() or None,
            telefono_emergencia=data.get('telefono_emergencia', '').strip() or None,
            estado=data.get('estado', True)
        )

        db.session.add(cliente)
        db.session.commit()

        return jsonify({"success": True, "message": "Cliente creado", "cliente": cliente.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear cliente: {str(e)}"}), 500


@main_bp.route('/admin/clientes/<int:id>', methods=['GET'])
@permiso_requerido('clientes')
def get_cliente(id):
    try:
        cliente = Cliente.query.get(id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404
        return jsonify(cliente.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error al obtener cliente: {str(e)}"}), 500


@main_bp.route('/admin/clientes/<int:id>', methods=['PUT'])
@permiso_requerido('clientes')
def update_cliente(id):
    try:
        cliente = Cliente.query.get(id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        data = request.get_json()

        if 'nombre' in data:
            cliente.nombre = data['nombre'].strip()
        if 'apellido' in data:
            cliente.apellido = data['apellido'].strip()
        if 'tipo_documento' in data:
            cliente.tipo_documento = data['tipo_documento'].strip() or None
        if 'numero_documento' in data:
            doc = str(data['numero_documento']).strip()
            existente = Cliente.query.filter_by(numero_documento=doc).first()
            if existente and existente.id != id:
                return jsonify({"error": "Ya existe otro cliente con este número de documento"}), 400
            cliente.numero_documento = doc
        if 'fecha_nacimiento' in data:
            try:
                cliente.fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
        if 'genero' in data:
            cliente.genero = data['genero'].strip() or None
        if 'telefono' in data:
            telefono = data['telefono'].strip() if data['telefono'] else None
            if telefono and not PHONE_REGEX.match(telefono):
                return jsonify({"error": "El teléfono debe contener solo números (7-15 dígitos)"}), 400
            cliente.telefono = telefono
        if 'correo' in data:
            correo = data['correo'].strip() if data['correo'] else None
            if correo and not EMAIL_REGEX.match(correo):
                return jsonify({"error": "Formato de correo electrónico inválido"}), 400
            cliente.correo = correo
        if 'municipio' in data:
            cliente.municipio = data['municipio'].strip() or None
        if 'direccion' in data:
            cliente.direccion = data['direccion'].strip() or None
        if 'departamento' in data:
            cliente.departamento = data['departamento'].strip() or None
        if 'barrio' in data:
            cliente.barrio = data['barrio'].strip() or None
        if 'codigo_postal' in data:
            cliente.codigo_postal = data['codigo_postal'].strip() or None
        if 'ocupacion' in data:
            cliente.ocupacion = data['ocupacion'].strip() or None
        if 'telefono_emergencia' in data:
            cliente.telefono_emergencia = data['telefono_emergencia'].strip() or None
        if 'estado' in data:
            cliente.estado = data['estado']

        db.session.commit()
        return jsonify({"success": True, "message": "Cliente actualizado", "cliente": cliente.to_dict()})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar cliente: {str(e)}"}), 500


@main_bp.route('/admin/clientes/<int:id>', methods=['DELETE'])
@permiso_requerido('clientes')
def delete_cliente(id):
    try:
        cliente = Cliente.query.get(id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        if cliente.estado:
            return jsonify({"error": "Debes desactivar el cliente antes de eliminarlo"}), 400

        if cliente.citas and len(cliente.citas) > 0:
            return jsonify({"error": "No se puede eliminar: tiene citas asociadas"}), 400
        if cliente.ventas and len(cliente.ventas) > 0:
            return jsonify({"error": "No se puede eliminar: tiene ventas asociadas"}), 400
        if cliente.pedidos and len(cliente.pedidos) > 0:
            return jsonify({"error": "No se puede eliminar: tiene pedidos asociados"}), 400

        db.session.delete(cliente)
        db.session.commit()
        return jsonify({"message": "Cliente eliminado correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar cliente: {str(e)}"}), 500


# ============================================================
# HISTORIAL DE FÓRMULAS
# ============================================================

@main_bp.route('/admin/clientes/<int:cliente_id>/historial', methods=['GET'])
@permiso_requerido('clientes')
def get_historial_cliente(cliente_id):
    try:
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        historiales = HistorialFormula.query.filter_by(cliente_id=cliente_id).all()
        return jsonify([historial.to_dict() for historial in historiales])
    except Exception as e:
        return jsonify({"error": f"Error al obtener historial: {str(e)}"}), 500


@main_bp.route('/admin/historial-formula', methods=['POST'])
@permiso_requerido('clientes')
def create_historial_formula():
    try:
        data = request.get_json()

        if not data.get('cliente_id'):
            return jsonify({"error": "El cliente_id es requerido"}), 400

        cliente = Cliente.query.get(data['cliente_id'])
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        historial = HistorialFormula(
            cliente_id=data['cliente_id'],
            descripcion=data.get('descripcion', '').strip() or None,
            od_esfera=data.get('od_esfera'),
            od_cilindro=data.get('od_cilindro'),
            od_eje=data.get('od_eje'),
            oi_esfera=data.get('oi_esfera'),
            oi_cilindro=data.get('oi_cilindro'),
            oi_eje=data.get('oi_eje')
        )

        db.session.add(historial)
        db.session.commit()
        return jsonify({"message": "Historial creado", "historial": historial.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear historial: {str(e)}"}), 500


@main_bp.route('/admin/historial-formula/<int:id>', methods=['DELETE'])
@permiso_requerido('clientes')
def delete_historial_formula(id):
    try:
        historial = HistorialFormula.query.get(id)
        if not historial:
            return jsonify({"error": "Historial no encontrado"}), 404

        db.session.delete(historial)
        db.session.commit()
        return jsonify({"message": "Fórmula eliminada correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar historial: {str(e)}"}), 500
    
@main_bp.route('/cliente/perfil', methods=['GET'])
@jwt_requerido
def get_cliente_perfil():
    """Obtiene el perfil del cliente asociado al usuario autenticado."""
    try:
        from app.Models.models import Usuario
        claims = get_usuario_actual()
        usuario_id = claims.get('id')
        usuario = Usuario.query.get(usuario_id)
        if not usuario or not usuario.cliente_id:
            return jsonify({"error": "No tienes un perfil de cliente asociado"}), 404
        cliente = Cliente.query.get(usuario.cliente_id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404
        return jsonify(cliente.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error al obtener perfil: {str(e)}"}), 500
    
    # ============================================================
# CLIENTE: VER SUS CITAS
# ============================================================
@main_bp.route('/cliente/citas', methods=['GET'])
@jwt_requerido
def get_mis_citas():
    """Cliente obtiene TODAS sus citas (ordenadas por fecha descendente)"""
    try:
        claims = get_usuario_actual()
        usuario_id = claims.get('id')
        
        usuario = Usuario.query.get(usuario_id)
        if not usuario or not usuario.cliente_id:
            return jsonify({"error": "No tienes un perfil de cliente asociado"}), 404
        
        citas = Cita.query.filter_by(cliente_id=usuario.cliente_id).order_by(Cita.fecha.desc(), Cita.hora.desc()).all()
        return jsonify([cita.to_dict() for cita in citas])
    except Exception as e:
        return jsonify({"error": f"Error al obtener citas: {str(e)}"}), 500

# ============================================================
# CLIENTE: crear un cita
# ============================================================

@main_bp.route('/cliente/citas', methods=['POST'])
@jwt_requerido
def crear_mi_cita():
    """Cliente crea una cita para sí mismo (usando su cliente_id del token)"""
    try:
        claims = get_usuario_actual()
        usuario = Usuario.query.get(claims.get('id'))
        if not usuario or not usuario.cliente_id:
            return jsonify({"error": "No tienes un perfil de cliente asociado"}), 404

        data = request.get_json()
        required_fields = ['servicio_id', 'empleado_id', 'fecha', 'hora']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Procesar fecha
        try:
            fecha_date = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Fecha inválida. Use YYYY-MM-DD"}), 400

        # Procesar hora
        hora_str = data['hora']
        try:
            if ':' in hora_str:
                hora_time = datetime.strptime(hora_str[:5], '%H:%M').time()
            else:
                hora_time = datetime.strptime(hora_str, '%H:%M:%S').time()
        except ValueError:
            return jsonify({"error": "Hora inválida. Use HH:MM"}), 400

        # Validar que no sea en el pasado
        ahora = datetime.utcnow()
        if datetime.combine(fecha_date, hora_time) < ahora:
            return jsonify({"error": "No se pueden programar citas en el pasado"}), 400

        # Obtener servicio
        servicio = Servicio.query.get(data['servicio_id'])
        if not servicio or not servicio.estado:
            return jsonify({"error": "Servicio no válido o inactivo"}), 400
        duracion = servicio.duracion_min

        # Validar disponibilidad (importa la función desde citas_routes o cópiala aquí)
        # Como está en otro archivo, la importaremos dinámicamente
        from .r_agenda import validar_disponibilidad_cita
        validacion = validar_disponibilidad_cita(
            empleado_id=data['empleado_id'],
            fecha=fecha_date,
            hora=hora_time,
            duracion=duracion,
            exclude_cita_id=None
        )
        if not validacion["disponible"]:
            return jsonify({"error": validacion["mensaje"]}), 400

        # Validar empleado activo
        empleado = Empleado.query.get(data['empleado_id'])
        if not empleado or not empleado.estado:
            return jsonify({"error": "El optómetra seleccionado no está activo"}), 400

        # Estado por defecto: "Pendiente" (buscar id 2 o el que corresponda)
        estado_pendiente = EstadoCita.query.filter_by(nombre='Pendiente').first()
        if not estado_pendiente:
            estado_pendiente = EstadoCita.query.first()

        cita = Cita(
            cliente_id=usuario.cliente_id,
            servicio_id=servicio.id,
            empleado_id=data['empleado_id'],
            estado_cita_id=estado_pendiente.id,
            metodo_pago=data.get('metodo_pago'),
            hora=hora_time,
            duracion=duracion,
            fecha=fecha_date
        )
        db.session.add(cita)
        db.session.commit()
        return jsonify({"message": "Cita agendada exitosamente", "cita": cita.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear cita: {str(e)}"}), 500

# ============================================================
# CLIENTE: CANCELAR UNA CITA PROPIA
# ============================================================
@main_bp.route('/cliente/citas/<int:cita_id>', methods=['DELETE'])
@jwt_requerido
def cancelar_mi_cita(cita_id):
    """Cliente cancela una de sus citas (solo si está Pendiente o Confirmada)"""
    try:
        claims = get_usuario_actual()
        usuario_id = claims.get('id')
        
        usuario = Usuario.query.get(usuario_id)
        if not usuario or not usuario.cliente_id:
            return jsonify({"error": "No tienes un perfil de cliente asociado"}), 404
        
        cita = Cita.query.get(cita_id)
        if not cita:
            return jsonify({"error": "Cita no encontrada"}), 404
        
        if cita.cliente_id != usuario.cliente_id:
            return jsonify({"error": "No puedes cancelar una cita que no te pertenece"}), 403
        
        # Estados permitidos para cancelar: 1 = Confirmada, 2 = Pendiente
        if cita.estado_cita_id not in [1, 2]:
            return jsonify({"error": "Solo se pueden cancelar citas pendientes o confirmadas"}), 400
        
        ahora = datetime.utcnow()
        fecha_hora_cita = datetime.combine(cita.fecha, cita.hora)
        if fecha_hora_cita < ahora:
            return jsonify({"error": "No se puede cancelar una cita que ya pasó"}), 400
        
        # Cambiar estado a Cancelada (id=4). Verifica que exista este estado en tu BD.
        cita.estado_cita_id = 4
        db.session.commit()
        
        cliente_nombre = f"{usuario.cliente.nombre} {usuario.cliente.apellido}"
        servicio_nombre = cita.servicio.nombre if cita.servicio else "servicio"
        fecha_str = cita.fecha.strftime('%d/%m/%Y')
        hora_str = cita.hora.strftime('%H:%M')
        
        return jsonify({
            "success": True,
            "message": "Cita cancelada correctamente",
            "cita": {
                "id": cita.id,
                "servicio": servicio_nombre,
                "fecha": fecha_str,
                "hora": hora_str,
                "cliente": cliente_nombre
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al cancelar cita: {str(e)}"}), 500