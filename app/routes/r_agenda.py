from flask import jsonify, request
from app.database import db
from app.Models.models import Cita, Servicio, Horario, EstadoCita, Empleado, Cliente, Venta, EstadoVenta, DetalleVenta, Novedad
from datetime import datetime, timedelta
import pytz
from app.routes import main_bp
from app.auth.decorators import permiso_requerido

# Zona horaria de Colombia
tz_colombia = pytz.timezone('America/Bogota')

# ============================================================
# MÓDULO: CITAS
# ============================================================

@main_bp.route('/citas', methods=['GET'])
@permiso_requerido("citas")
def get_citas():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        pagination = Cita.query.order_by(Cita.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return jsonify({
            'data': [cita.to_dict() for cita in pagination.items],
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total_pages': pagination.pages
        })
    except Exception as e:
        return jsonify({"error": f"Error al obtener citas: {str(e)}"}), 500

@main_bp.route('/citas/<int:id>', methods=['GET'])
@permiso_requerido("citas")
def get_cita(id):
    try:
        cita = Cita.query.get(id)
        if not cita:
            return jsonify({"error": "Cita no encontrada"}), 404
        return jsonify(cita.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error al obtener la cita: {str(e)}"}), 500


@main_bp.route('/citas', methods=['POST'])
@permiso_requerido("citas")
def create_cita():
    try:
        data = request.get_json()
        required_fields = ['cliente_id', 'servicio_id', 'empleado_id', 'estado_cita_id', 'fecha', 'hora']
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Procesar fecha y hora
        try:
            fecha_date = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
        
        hora_str = data['hora']
        try:
            if hora_str.count(':') == 1:
                hora_time = datetime.strptime(hora_str, '%H:%M').time()
            else:
                hora_time = datetime.strptime(hora_str, '%H:%M:%S').time()
        except ValueError:
            return jsonify({"error": "Formato de hora inválido. Use HH:MM o HH:MM:SS"}), 400

        # Validar que no sea en el pasado
        ahora = datetime.utcnow()
        fecha_hora_cita = datetime.combine(fecha_date, hora_time)
        if fecha_hora_cita < ahora:
            return jsonify({"error": "No se pueden programar citas en el pasado"}), 400

        # Obtener servicio y duración
        servicio = Servicio.query.get(data['servicio_id'])
        if not servicio:
            return jsonify({"error": "El servicio especificado no existe"}), 404
        if not servicio.estado:
            return jsonify({"error": "El servicio no está activo"}), 400
        duracion = servicio.duracion_min

        # Validar disponibilidad del empleado
        validacion = validar_disponibilidad_cita(
            empleado_id=data['empleado_id'],
            fecha=fecha_date,
            hora=hora_time,
            duracion=duracion,
            exclude_cita_id=None
        )
        if not validacion["disponible"]:
            return jsonify({"error": validacion["mensaje"]}), 400

        # Validar cliente y empleado activos
        empleado = Empleado.query.get(data['empleado_id'])
        cliente = Cliente.query.get(data['cliente_id'])
        if not empleado or not empleado.estado:
            return jsonify({"error": "El optómetra seleccionado no está activo"}), 400
        if not cliente or not cliente.estado:
            return jsonify({"error": "El cliente seleccionado está inactivo"}), 400

        # Validar que el estado de cita exista
        estado_cita = EstadoCita.query.get(data['estado_cita_id'])
        if not estado_cita:
            return jsonify({"error": "Estado de cita inválido"}), 400

        # Crear cita
        cita = Cita(
            cliente_id=data['cliente_id'],
            servicio_id=servicio.id,
            empleado_id=data['empleado_id'],
            estado_cita_id=data['estado_cita_id'],
            metodo_pago=data.get('metodo_pago'),
            hora=hora_time,
            duracion=duracion,
            fecha=fecha_date
        )
        db.session.add(cita)
        db.session.commit()
        return jsonify({"message": "Cita creada", "cita": cita.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear cita: {str(e)}"}), 500

def validar_disponibilidad_cita(empleado_id, fecha, hora, duracion, exclude_cita_id=None):
    """
    Retorna dict con 'disponible' (bool) y 'mensaje' (str).
    """
    # 1. Verificar novedades (vacaciones, incapacidades, permisos)
    novedad = Novedad.query.filter(
        Novedad.empleado_id == empleado_id,
        Novedad.fecha_inicio <= fecha,
        Novedad.fecha_fin >= fecha,
        Novedad.activo == True
    ).first()
    if novedad:
        empleado_nombre = Empleado.query.get(empleado_id).nombre
        fecha_inicio_str = novedad.fecha_inicio.strftime('%d/%m/%Y')
        fecha_fin_str = novedad.fecha_fin.strftime('%d/%m/%Y')
        motivo_str = f": {novedad.motivo}" if novedad.motivo else ""
        
        if novedad.hora_inicio is None and novedad.hora_fin is None:
            return {
                "disponible": False,
                "mensaje": f"El empleado {empleado_nombre} no está disponible por {novedad.tipo} del {fecha_inicio_str} al {fecha_fin_str}{motivo_str}."
            }
        if novedad.hora_inicio and novedad.hora_fin:
            if novedad.hora_inicio <= hora <= novedad.hora_fin:
                hora_inicio_str = novedad.hora_inicio.strftime('%H:%M')
                hora_fin_str = novedad.hora_fin.strftime('%H:%M')
                return {
                    "disponible": False,
                    "mensaje": f"El empleado {empleado_nombre} no está disponible el {fecha_inicio_str} de {hora_inicio_str} a {hora_fin_str} por {novedad.tipo}{motivo_str}."
                }

    # 2. Verificar horario laboral
    dia_semana = fecha.weekday()
    horario = Horario.query.filter_by(empleado_id=empleado_id, dia=dia_semana, activo=True).first()
    if not horario:
        return {"disponible": False, "mensaje": "El empleado no tiene horario asignado para este día"}
    if not (horario.hora_inicio <= hora <= horario.hora_final):
        return {
            "disponible": False,
            "mensaje": f"El empleado solo trabaja de {horario.hora_inicio.strftime('%H:%M')} a {horario.hora_final.strftime('%H:%M')}"
        }

    # 3. Verificar solapamiento con otras citas
    inicio_solicitado = datetime.combine(fecha, hora)
    fin_solicitado = inicio_solicitado + timedelta(minutes=duracion)
    citas = Cita.query.filter(
        Cita.empleado_id == empleado_id,
        Cita.fecha == fecha
    )
    if exclude_cita_id:
        citas = citas.filter(Cita.id != exclude_cita_id)

    for cita in citas:
        inicio_cita = datetime.combine(cita.fecha, cita.hora)
        fin_cita = inicio_cita + timedelta(minutes=cita.duracion or 30)
        if inicio_solicitado < fin_cita and fin_solicitado > inicio_cita:
            return {
                "disponible": False,
                "mensaje": f"El empleado ya tiene una cita programada desde las {cita.hora.strftime('%H:%M')}"
            }

    return {"disponible": True, "mensaje": "Horario disponible"}

@main_bp.route('/citas/<int:id>', methods=['PUT'])
@permiso_requerido("citas")
def update_cita(id):
    try:
        cita = Cita.query.get(id)
        if not cita:
            return jsonify({"error": "Cita no encontrada"}), 404

        # No permitir modificar cita cancelada
        estado_actual_obj = EstadoCita.query.get(cita.estado_cita_id)
        if estado_actual_obj and estado_actual_obj.nombre.lower() == "cancelada":
            return jsonify({"error": "No se puede modificar una cita que ya está cancelada"}), 400

        # No permitir modificar cita pasada
        ahora = datetime.utcnow()
        fecha_cita_actual = datetime.combine(cita.fecha, cita.hora)
        if fecha_cita_actual < ahora:
            return jsonify({"error": "No se puede modificar una cita que ya pasó"}), 400

        data = request.get_json()
        
        # Variables para control de cambios
        nuevo_empleado_id = data.get('empleado_id', cita.empleado_id)
        nueva_fecha_str = data.get('fecha')
        nueva_hora_str = data.get('hora')
        nuevo_servicio_id = data.get('servicio_id', cita.servicio_id)
        nuevo_estado_id = data.get('estado_cita_id', cita.estado_cita_id)
        
        # Procesar nueva fecha/hora si vienen
        fecha_final = cita.fecha
        hora_final = cita.hora
        if nueva_fecha_str:
            try:
                fecha_final = datetime.strptime(nueva_fecha_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400
        if nueva_hora_str:
            try:
                if nueva_hora_str.count(':') == 1:
                    hora_final = datetime.strptime(nueva_hora_str, '%H:%M').time()
                else:
                    hora_final = datetime.strptime(nueva_hora_str, '%H:%M:%S').time()
            except ValueError:
                return jsonify({"error": "Formato de hora inválido. Use HH:MM o HH:MM:SS"}), 400
        
        # Validar que la nueva fecha/hora no sea pasada
        nueva_fecha_hora = datetime.combine(fecha_final, hora_final)
        if nueva_fecha_hora < ahora:
            return jsonify({"error": "No se puede reprogramar la cita a una fecha/hora pasada"}), 400
        
        # Obtener duración (puede cambiar si cambia servicio)
        duracion = cita.duracion
        if nuevo_servicio_id != cita.servicio_id:
            servicio = Servicio.query.get(nuevo_servicio_id)
            if not servicio:
                return jsonify({"error": "El servicio especificado no existe"}), 404
            if not servicio.estado:
                return jsonify({"error": "El servicio no está activo"}), 400
            duracion = servicio.duracion_min
        
        # Validar disponibilidad si cambió empleado, fecha, hora o servicio
        if (nuevo_empleado_id != cita.empleado_id or
            nueva_fecha_str is not None or
            nueva_hora_str is not None or
            nuevo_servicio_id != cita.servicio_id):
            validacion = validar_disponibilidad_cita(
                empleado_id=nuevo_empleado_id,
                fecha=fecha_final,
                hora=hora_final,
                duracion=duracion,
                exclude_cita_id=cita.id
            )
            if not validacion["disponible"]:
                return jsonify({"error": validacion["mensaje"]}), 400
        
        # Actualizar campos de la cita
        if 'cliente_id' in data:
            cliente = Cliente.query.get(data['cliente_id'])
            if not cliente or not cliente.estado:
                return jsonify({"error": "Cliente no válido o inactivo"}), 400
            cita.cliente_id = data['cliente_id']
        if 'empleado_id' in data:
            empleado = Empleado.query.get(data['empleado_id'])
            if not empleado or not empleado.estado:
                return jsonify({"error": "Empleado no válido o inactivo"}), 400
            cita.empleado_id = data['empleado_id']
        if 'servicio_id' in data:
            cita.servicio_id = nuevo_servicio_id
            cita.duracion = duracion
        if 'fecha' in data:
            cita.fecha = fecha_final
        if 'hora' in data:
            cita.hora = hora_final
        if 'metodo_pago' in data:
            cita.metodo_pago = data['metodo_pago']
        if 'estado_cita_id' in data:
            # Validar que el nuevo estado exista
            nuevo_estado = EstadoCita.query.get(nuevo_estado_id)
            if not nuevo_estado:
                return jsonify({"error": "Estado de cita inválido"}), 400
            
            # --- LÓGICA DE COMPLETADO (CREACIÓN DE VENTA) ---
            if nuevo_estado_id == 3 and cita.estado_cita_id != 3:
                # Verificar que no tenga ya una venta asociada
                if hasattr(cita, 'venta') and cita.venta:
                    return jsonify({"error": "Esta cita ya generó una venta"}), 400
                
                # Obtener servicio (ya debería estar actualizado)
                servicio_actual = Servicio.query.get(cita.servicio_id)
                if not servicio_actual:
                    return jsonify({"error": "Servicio no encontrado"}), 404
                
                # Obtener estado de venta 'completada'
                estado_venta = EstadoVenta.query.filter_by(nombre='completada').first()
                if not estado_venta:
                    return jsonify({"error": "Estado 'completada' no encontrado en EstadoVenta"}), 500
                
                # Crear la venta
                venta = Venta(
                    cita_id=cita.id,
                    cliente_id=cita.cliente_id,
                    fecha_venta=datetime.utcnow(),
                    total=servicio_actual.precio,
                    metodo_pago=cita.metodo_pago,
                    estado_id=estado_venta.id
                )
                db.session.add(venta)
                db.session.flush()  # Para obtener el ID de la venta
                
                # Crear detalle de venta (servicio)
                detalle_venta = DetalleVenta(
                    venta_id=venta.id,
                    servicio_id=servicio_actual.id,
                    cantidad=1,
                    precio_unitario=servicio_actual.precio,
                    subtotal=servicio_actual.precio
                )
                db.session.add(detalle_venta)
            
            cita.estado_cita_id = nuevo_estado_id

        db.session.commit()
        return jsonify({"message": "Cita actualizada", "cita": cita.to_dict()})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar cita: {str(e)}"}), 500


@main_bp.route('/citas/<int:id>', methods=['DELETE'])
@permiso_requerido("citas")
def delete_cita(id):
    try:
        cita = Cita.query.get(id)
        if not cita:
            return jsonify({"error": "Cita no encontrada"}), 404
        
        # No permitir eliminar citas completadas
        estado_actual = EstadoCita.query.get(cita.estado_cita_id)
        if estado_actual and estado_actual.nombre.lower() == 'completada':
            return jsonify({"error": "No se puede eliminar una cita que ya está completada"}), 400
        
        # Opcional: también se podría prohibir eliminar citas pasadas, pero no es obligatorio
        ahora = datetime.utcnow()
        fecha_cita = datetime.combine(cita.fecha, cita.hora)
        if fecha_cita < ahora:
            return jsonify({"error": "No se puede eliminar una cita que ya pasó"}), 400
        
        db.session.delete(cita)
        db.session.commit()
        return jsonify({"message": "Cita eliminada correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar cita: {str(e)}"}), 500


# ============================================================
# MÓDULO: SERVICIOS
# ============================================================

@main_bp.route('/servicios', methods=['GET'])
def get_servicios():
    try:
        servicios = Servicio.query.order_by(Servicio.nombre.asc()).all()
        return jsonify([servicio.to_dict() for servicio in servicios])
    except Exception as e:
        return jsonify({"error": "Error al obtener servicios"}), 500


@main_bp.route('/servicios', methods=['POST'])
@permiso_requerido("servicios")
def create_servicio():
    try:
        data = request.get_json()
        
        # Limpiar y validar nombre
        nombre = " ".join(data.get('nombre', '').split()).strip()
        precio = float(data.get('precio', 0))
        duracion = int(data.get('duracion_min', 30))

        # 1. VALIDACIÓN: Datos básicos
        if not nombre:
            return jsonify({"error": "El nombre del servicio es obligatorio"}), 400
        if precio <= 0:
            return jsonify({"error": "El precio debe ser mayor a 0"}), 400
        if duracion <= 0:
            return jsonify({"error": "La duración debe ser mayor a 0 minutos"}), 400

        # 2. VALIDACIÓN: Unicidad (case insensitive)
        if Servicio.query.filter(Servicio.nombre.ilike(nombre)).first():
            return jsonify({"error": f"El servicio '{nombre}' ya existe"}), 400

        servicio = Servicio(
            nombre=nombre,
            duracion_min=duracion,
            precio=precio,
            descripcion=data.get('descripcion', '').strip(),
            estado=data.get('estado', True)
        )
        
        db.session.add(servicio)
        db.session.commit()
        
        return jsonify({"message": "Servicio creado", "servicio": servicio.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear servicio: {str(e)}"}), 500


@main_bp.route('/servicios/<int:id>', methods=['PUT'])
@permiso_requerido("servicios")
def update_servicio(id):
    try:
        servicio = Servicio.query.get(id)
        if not servicio:
            return jsonify({"error": "Servicio no encontrado"}), 404
            
        data = request.get_json()
        
        # Si se intenta cambiar el nombre, validar que no choque con otro
        if 'nombre' in data:
            nombre = " ".join(data['nombre'].split()).strip()
            existente = Servicio.query.filter(
                Servicio.nombre.ilike(nombre), 
                Servicio.id != id
            ).first()
            if existente:
                return jsonify({"error": "Ya existe otro servicio con ese nombre"}), 400
            servicio.nombre = nombre

        # Actualización de otros campos con validaciones
        if 'precio' in data:
            precio = float(data['precio'])
            if precio <= 0:
                return jsonify({"error": "El precio debe ser mayor a 0"}), 400
            servicio.precio = precio
            
        if 'duracion_min' in data:
            duracion = int(data['duracion_min'])
            if duracion <= 0:
                return jsonify({"error": "La duración debe ser mayor a 0 minutos"}), 400
            servicio.duracion_min = duracion
            
        if 'descripcion' in data:
            servicio.descripcion = data['descripcion'].strip()
            
        if 'estado' in data:
            # VALIDACIÓN: No desactivar si tiene citas pendientes
            if not data['estado'] and servicio.citas:
                citas_pendientes = [c for c in servicio.citas if c.estado_cita_id == 1]  # 1 = pendiente
                if citas_pendientes:
                    return jsonify({"error": "No puedes desactivar un servicio que tiene citas pendientes"}), 400
            servicio.estado = bool(data['estado'])

        db.session.commit()
        return jsonify({"message": "Servicio actualizado", "servicio": servicio.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar servicio: {str(e)}"}), 500


@main_bp.route('/servicios/<int:id>', methods=['DELETE'])
@permiso_requerido("servicios")
def delete_servicio(id):
    try:
        servicio = Servicio.query.get(id)
        if not servicio:
            return jsonify({"error": "Servicio no encontrado"}), 404

        # REGLA DE NEGOCIO: No borrar si hay citas asociadas
        if servicio.citas and len(servicio.citas) > 0:
            return jsonify({
                "error": "No se puede eliminar. Este servicio tiene citas registradas. Desactívelo en su lugar."
            }), 400

        db.session.delete(servicio)
        db.session.commit()
        return jsonify({"message": "Servicio eliminado correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar servicio"}), 500


# ============================================================
# MÓDULO: HORARIOS
# ============================================================

@main_bp.route('/horario', methods=['GET'])
@permiso_requerido("empleados")
def get_horarios():
    try:
        horarios = Horario.query.all()
        return jsonify([horario.to_dict() for horario in horarios])
    except Exception as e:
        return jsonify({"error": "Error al obtener horarios"}), 500


@main_bp.route('/horario', methods=['POST'])
@permiso_requerido("empleados")
def create_horario():
    try:
        data = request.get_json()
        required_fields = ['empleado_id', 'hora_inicio', 'hora_final', 'dia']
        
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Validar día
        if not isinstance(data['dia'], int) or data['dia'] not in range(0, 7):
            return jsonify({"error": "El día debe ser un número entre 0 (lunes) y 6 (domingo)"}), 400

        # Validar horas
        try:
            hora_inicio = datetime.strptime(data['hora_inicio'], '%H:%M').time()
            hora_final = datetime.strptime(data['hora_final'], '%H:%M').time()
        except ValueError:
            return jsonify({"error": "Formato de hora inválido. Use HH:MM"}), 400

        if hora_final <= hora_inicio:
            return jsonify({
                "error": "La hora final debe ser posterior a la hora de inicio. Verifique que el horario tenga al menos 1 minuto de duración."
            }), 400

        # VALIDACIÓN: Empleado existe y está activo
        empleado = Empleado.query.get(data['empleado_id'])
        if not empleado or not empleado.estado:
            return jsonify({
                "error": f"El empleado '{empleado.nombre if empleado else 'desconocido'}' está inactivo. No se pueden crear horarios para empleados inactivos."
            }), 400

        # VALIDACIÓN: No duplicar horario para mismo empleado, día y activo
        horario_existente = Horario.query.filter_by(
            empleado_id=data['empleado_id'],
            dia=data['dia'],
            activo=True
        ).first()
        
        if horario_existente:
            empleado_nombre = empleado.nombre
            dia_nombre = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][data['dia']]
            return jsonify({
                "error": f"El empleado {empleado_nombre} ya tiene un horario activo para el día {dia_nombre}. Solo puede tener un horario por día."
            }), 400

        horario = Horario(
            empleado_id=data['empleado_id'],
            dia=data['dia'],
            hora_inicio=hora_inicio,
            hora_final=hora_final,
            activo=data.get('activo', True)
        )
        
        db.session.add(horario)
        db.session.commit()
        
        return jsonify({"message": "Horario creado", "horario": horario.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear horario: {str(e)}"}), 500


@main_bp.route('/horario/<int:id>', methods=['PUT'])
@permiso_requerido("empleados")
def update_horario(id):
    try:
        horario = Horario.query.get(id)
        if not horario:
            return jsonify({"error": "Horario no encontrado"}), 404
            
        data = request.get_json()
        
        if 'empleado_id' in data:
            empleado = Empleado.query.get(data['empleado_id'])
            if not empleado or not empleado.estado:
                return jsonify({"error": "Empleado no válido o inactivo"}), 400
            horario.empleado_id = data['empleado_id']
            
        if 'dia' in data:
            if not isinstance(data['dia'], int) or data['dia'] not in range(0, 7):
                return jsonify({"error": "El día debe ser entre 0 y 6"}), 400
            horario.dia = data['dia']
            
        if 'hora_inicio' in data:
            try:
                horario.hora_inicio = datetime.strptime(data['hora_inicio'], '%H:%M').time()
            except ValueError:
                return jsonify({"error": "Formato de hora inválido. Use HH:MM"}), 400
            
        if 'hora_final' in data:
            try:
                horario.hora_final = datetime.strptime(data['hora_final'], '%H:%M').time()
            except ValueError:
                return jsonify({"error": "Formato de hora inválido. Use HH:MM"}), 400
            
        if 'activo' in data:
            horario.activo = data['activo']

        # Validar que hora_final > hora_inicio
        if horario.hora_final <= horario.hora_inicio:
            return jsonify({"error": "La hora final debe ser mayor que la hora inicio"}), 400

        db.session.commit()
        return jsonify({"message": "Horario actualizado", "horario": horario.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar horario: {str(e)}"}), 500


@main_bp.route('/horario/<int:id>', methods=['DELETE'])
@permiso_requerido("empleados")
def delete_horario(id):
    try:
        horario = Horario.query.get(id)
        if not horario:
            return jsonify({"error": "Horario no encontrado"}), 404
            
        db.session.delete(horario)
        db.session.commit()
        return jsonify({"message": "Horario eliminado correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar horario: {str(e)}"}), 500


@main_bp.route('/horario/empleado/<int:empleado_id>', methods=['GET'])
@permiso_requerido("empleados")
def get_horarios_por_empleado(empleado_id):
    try:
        horarios = Horario.query.filter_by(empleado_id=empleado_id).all()
        return jsonify([h.to_dict() for h in horarios])
    except Exception as e:
        return jsonify({"error": "Error al obtener horarios"}), 500


@main_bp.route('/empleados/<int:empleado_id>/horarios', methods=['GET'])
@permiso_requerido("empleados")
def get_horarios_empleado(empleado_id):
    try:
        horarios = Horario.query.filter_by(empleado_id=empleado_id).all()
        return jsonify([horario.to_dict() for horario in horarios])
    except Exception as e:
        return jsonify({"error": "Error al obtener horarios del empleado"}), 500

# ============================================================
# MÓDULO: VERIFICAR DISPONIBILIDAD
# ============================================================

@main_bp.route('/verificar-disponibilidad', methods=['GET'])
def verificar_disponibilidad():
    """
    Verifica si un empleado está disponible en una fecha y hora específicas.
    Query params:
        empleado_id (int): ID del empleado
        fecha (str): YYYY-MM-DD
        hora (str): HH:MM
        servicio_id (int): ID del servicio (para obtener duración automática)
        duracion (int): duración en minutos (opcional, se usa si no hay servicio_id)
        exclude_cita_id (int): ID de una cita a excluir (para edición)
    """
    try:
        empleado_id = request.args.get('empleado_id', type=int)
        fecha_str = request.args.get('fecha')
        hora_str = request.args.get('hora')
        servicio_id = request.args.get('servicio_id', type=int)
        duracion = request.args.get('duracion', type=int)
        exclude_cita_id = request.args.get('exclude_cita_id', type=int)

        # Validar parámetros obligatorios
        if not empleado_id or not fecha_str or not hora_str:
            return jsonify({
                "disponible": False,
                "mensaje": "Faltan parámetros: empleado_id, fecha, hora"
            }), 400

        # Validar que el empleado exista y esté activo
        empleado = Empleado.query.get(empleado_id)
        if not empleado or not empleado.estado:
            return jsonify({
                "disponible": False,
                "mensaje": "El empleado no está activo o no existe"
            }), 400

        # Obtener duración desde servicio si se proporciona
        if servicio_id:
            servicio = Servicio.query.get(servicio_id)
            if servicio:
                duracion = servicio.duracion_min
        # Si no hay servicio ni duración, usar valor por defecto seguro
        if not duracion:
            duracion = 30

        # Procesar fecha y hora
        try:
            fecha_date = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hora_time = datetime.strptime(hora_str, '%H:%M').time()
        except ValueError:
            return jsonify({
                "disponible": False,
                "mensaje": "Formato de fecha u hora inválido (use YYYY-MM-DD y HH:MM)"
            }), 400

        # Validar que no sea en el pasado (usando UTC)
        ahora = datetime.utcnow()
        fecha_hora_solicitada = datetime.combine(fecha_date, hora_time)
        if fecha_hora_solicitada < ahora:
            return jsonify({
                "disponible": False,
                "mensaje": "No se pueden verificar disponibilidad en el pasado"
            }), 400

        # ============================================================
        # VERIFICAR NOVEDADES (vacaciones, incapacidades, permisos)
        # ============================================================
        novedad = Novedad.query.filter(
            Novedad.empleado_id == empleado_id,
            Novedad.fecha_inicio <= fecha_date,
            Novedad.fecha_fin >= fecha_date,
            Novedad.activo == True
        ).first()
        if novedad:
            empleado_nombre = empleado.nombre
            fecha_inicio_str = novedad.fecha_inicio.strftime('%d/%m/%Y')
            fecha_fin_str = novedad.fecha_fin.strftime('%d/%m/%Y')
            motivo_str = f": {novedad.motivo}" if novedad.motivo else ""
            if novedad.hora_inicio is None and novedad.hora_fin is None:
                return jsonify({
                    "disponible": False,
                    "mensaje": f"El empleado {empleado_nombre} no está disponible por {novedad.tipo} del {fecha_inicio_str} al {fecha_fin_str}{motivo_str}."
                })
            if novedad.hora_inicio and novedad.hora_fin:
                if novedad.hora_inicio <= hora_time <= novedad.hora_fin:
                    hora_inicio_str = novedad.hora_inicio.strftime('%H:%M')
                    hora_fin_str = novedad.hora_fin.strftime('%H:%M')
                    return jsonify({
                        "disponible": False,
                        "mensaje": f"El empleado {empleado_nombre} no está disponible el {fecha_inicio_str} de {hora_inicio_str} a {hora_fin_str} por {novedad.tipo}{motivo_str}."
                    })

        # ============================================================
        # VERIFICAR HORARIO LABORAL
        # ============================================================
        dia_semana = fecha_date.weekday()
        horario = Horario.query.filter_by(
            empleado_id=empleado_id, dia=dia_semana, activo=True
        ).first()

        if not horario:
            return jsonify({
                "disponible": False,
                "mensaje": "El empleado no tiene horario asignado para este día"
            })

        # Validar que la hora esté dentro del rango laboral
        if hora_time < horario.hora_inicio or hora_time > horario.hora_final:
            return jsonify({
                "disponible": False,
                "mensaje": f"El empleado solo trabaja de {horario.hora_inicio.strftime('%H:%M')} a {horario.hora_final.strftime('%H:%M')}",
                "horario": {
                    "inicio": horario.hora_inicio.strftime('%H:%M'),
                    "fin": horario.hora_final.strftime('%H:%M')
                }
            })

        # ============================================================
        # VERIFICAR SOLAPAMIENTO CON OTRAS CITAS
        # ============================================================
        inicio_solicitado = datetime.combine(fecha_date, hora_time)
        fin_solicitado = inicio_solicitado + timedelta(minutes=duracion)

        query = Cita.query.filter(
            Cita.empleado_id == empleado_id,
            Cita.fecha == fecha_date
        )
        if exclude_cita_id:
            query = query.filter(Cita.id != exclude_cita_id)

        for cita in query.all():
            inicio_cita = datetime.combine(cita.fecha, cita.hora)
            fin_cita = inicio_cita + timedelta(minutes=cita.duracion or 30)
            if inicio_solicitado < fin_cita and fin_solicitado > inicio_cita:
                return jsonify({
                    "disponible": False,
                    "mensaje": f"El empleado ya tiene una cita programada desde las {cita.hora.strftime('%H:%M')}",
                    "horario": {
                        "inicio": horario.hora_inicio.strftime('%H:%M'),
                        "fin": horario.hora_final.strftime('%H:%M')
                    }
                })

        # Si todo está bien, retornar disponible
        return jsonify({
            "disponible": True,
            "mensaje": "Horario disponible",
            "horario": {
                "inicio": horario.hora_inicio.strftime('%H:%M'),
                "fin": horario.hora_final.strftime('%H:%M')
            }
        })

    except Exception as e:
        return jsonify({
            "disponible": False,
            "mensaje": f"Error interno al verificar disponibilidad: {str(e)}"
        }), 500

# ============================================================
# DISPONIBILIDAD MÚLTIPLE 
# ============================================================
@main_bp.route('/verificar-disponibilidad-multiple', methods=['GET'])
def verificar_disponibilidad_multiple():
    """
    Retorna todas las horas disponibles para un servicio en una fecha,
    con el empleado sugerido para cada hora.
    Query params OBLIGATORIOS:
        servicio_id (int)
        fecha (str) YYYY-MM-DD
    Opcionales:
        intervalo_minutos (int, default 30)
        empleados_ids (str, ej "1,2,3")
    """
    try:
        # Obtener parámetros
        servicio_id = request.args.get('servicio_id', type=int)
        fecha_str = request.args.get('fecha')
        intervalo = request.args.get('intervalo_minutos', 30, type=int)
        empleados_ids_str = request.args.get('empleados_ids', '')

        # Validaciones básicas
        if not servicio_id:
            return jsonify({"error": "Falta parámetro: servicio_id"}), 400
        if not fecha_str:
            return jsonify({"error": "Falta parámetro: fecha"}), 400

        if intervalo < 1:
            intervalo = 30

        # Obtener servicio
        servicio = Servicio.query.get(servicio_id)
        if not servicio:
            return jsonify({"error": "Servicio no encontrado"}), 404
        if not servicio.estado:
            return jsonify({"error": "Servicio no está activo"}), 400
        duracion = servicio.duracion_min

        # Validar fecha
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400

        hoy_utc = datetime.utcnow().date()
        if fecha < hoy_utc:
            return jsonify({"error": "No se puede consultar disponibilidad en fechas pasadas"}), 400

        # Obtener empleados a evaluar
        if empleados_ids_str:
            ids = [int(x) for x in empleados_ids_str.split(',') if x.strip().isdigit()]
            empleados = Empleado.query.filter(Empleado.id.in_(ids), Empleado.estado == True).all()
        else:
            empleados = Empleado.query.filter_by(estado=True).all()

        if not empleados:
            return jsonify({"horas_disponibles": []})

        from collections import defaultdict
        dia_semana = fecha.weekday()  # 0=lunes, 6=domingo

        # ------------------------------------------------------------
        # PRECARGAR DATOS POR EMPLEADO
        # ------------------------------------------------------------
        horarios_por_emp = {}
        novedades_por_emp = {}
        for emp in empleados:
            horarios_por_emp[emp.id] = Horario.query.filter_by(empleado_id=emp.id, activo=True).all()
            novedades_por_emp[emp.id] = Novedad.query.filter(
                Novedad.empleado_id == emp.id,
                Novedad.fecha_inicio <= fecha,
                Novedad.fecha_fin >= fecha,
                Novedad.activo == True
            ).all()

        # Citas del día (una sola consulta)
        citas_por_empleado = defaultdict(list)
        todas_citas = Cita.query.filter(Cita.fecha == fecha).all()
        ids_empleados = {emp.id for emp in empleados}
        for cita in todas_citas:
            if cita.empleado_id in ids_empleados:
                inicio_cita = datetime.combine(cita.fecha, cita.hora)
                fin_cita = inicio_cita + timedelta(minutes=cita.duracion or 30)
                citas_por_empleado[cita.empleado_id].append((inicio_cita, fin_cita))

        # ------------------------------------------------------------
        # CALCULAR RANGO HORARIO GLOBAL (mínimo inicio, máximo fin)
        # ------------------------------------------------------------
        hora_global_inicio = 24 * 60   # 1440 minutos
        hora_global_fin = 0
        # Diccionario para almacenar el horario específico de cada empleado en este día
        horario_empleado_dia = {}

        for emp in empleados:
            # Buscar el primer horario activo para este día (asumimos solo uno)
            horario_dia = None
            for h in horarios_por_emp.get(emp.id, []):
                if h.dia == dia_semana and h.activo:
                    horario_dia = h
                    break
            if not horario_dia:
                continue

            inicio_min = horario_dia.hora_inicio.hour * 60 + horario_dia.hora_inicio.minute
            fin_min = horario_dia.hora_final.hour * 60 + horario_dia.hora_final.minute
            horario_empleado_dia[emp.id] = horario_dia

            # Actualizar rango global
            if inicio_min < hora_global_inicio:
                hora_global_inicio = inicio_min
            if fin_min > hora_global_fin:
                hora_global_fin = fin_min

        # Si no hay ningún empleado con horario ese día, retornar vacío
        if hora_global_inicio == 24*60 or hora_global_fin == 0:
            return jsonify({"horas_disponibles": []})

        # ------------------------------------------------------------
        # GENERAR TODAS LAS HORAS POSIBLES (basadas en rango global)
        # ------------------------------------------------------------
        horas_posibles = []
        current_min = hora_global_inicio
        while current_min + duracion <= hora_global_fin:
            h = current_min // 60
            m = current_min % 60
            horas_posibles.append(f"{h:02d}:{m:02d}")
            current_min += intervalo

        # ------------------------------------------------------------
        # EVALUAR CADA HORA: buscar cualquier empleado disponible
        # ------------------------------------------------------------
        resultado = []
        for hora_str in horas_posibles:
            hora_time = datetime.strptime(hora_str, '%H:%M').time()
            inicio_solicitado = datetime.combine(fecha, hora_time)
            fin_solicitado = inicio_solicitado + timedelta(minutes=duracion)

            empleado_asignado = None
            for emp in empleados:
                # Obtener el horario específico de este empleado para el día
                horario_emp = horario_empleado_dia.get(emp.id)
                if not horario_emp:
                    continue

                # 1. Verificar novedades (día completo o rango horario)
                bloqueado = False
                for nov in novedades_por_emp.get(emp.id, []):
                    if nov.hora_inicio is None and nov.hora_fin is None:
                        bloqueado = True
                        break
                    if nov.hora_inicio and nov.hora_fin:
                        if nov.hora_inicio <= hora_time <= nov.hora_fin:
                            bloqueado = True
                            break
                if bloqueado:
                    continue

                # 2. Verificar que la hora esté dentro del horario laboral del empleado
                if hora_time < horario_emp.hora_inicio or hora_time > horario_emp.hora_final:
                    continue

                # 3. Verificar que el servicio quepa antes del fin de jornada
                fin_jornada = datetime.combine(fecha, horario_emp.hora_final)
                if fin_solicitado > fin_jornada:
                    continue

                # 4. Verificar conflictos con citas existentes
                conflicto = False
                for inicio_cita, fin_cita in citas_por_empleado.get(emp.id, []):
                    if inicio_solicitado < fin_cita and fin_solicitado > inicio_cita:
                        conflicto = True
                        break
                if conflicto:
                    continue

                # Si llegamos aquí, el empleado está disponible
                empleado_asignado = emp.id
                break

            if empleado_asignado:
                resultado.append({
                    "hora": hora_str,
                    "empleado_id": empleado_asignado
                })

        return jsonify({
            "fecha": fecha_str,
            "servicio_id": servicio_id,
            "duracion": duracion,
            "intervalo_minutos": intervalo,
            "horas_disponibles": resultado
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error interno: {str(e)}"}), 500
# ============================================================
# MÓDULO: ESTADOS DE CITA
# ============================================================

@main_bp.route('/estado-cita', methods=['GET'])
def get_estados_cita():
    try:
        estados = EstadoCita.query.all()
        return jsonify([estado.to_dict() for estado in estados])
    except Exception as e:
        return jsonify({"error": "Error al obtener estados de cita"}), 500


@main_bp.route('/estado-cita', methods=['POST'])
@permiso_requerido("citas")
def create_estado_cita():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400
            
        nombre = " ".join(data['nombre'].split()).strip()
        
        # Validar unicidad
        if EstadoCita.query.filter(EstadoCita.nombre.ilike(nombre)).first():
            return jsonify({"error": f"El estado '{nombre}' ya existe"}), 400
            
        estado = EstadoCita(nombre=nombre)
        db.session.add(estado)
        db.session.commit()
        
        return jsonify({"message": "Estado de cita creado", "estado": estado.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear estado de cita: {str(e)}"}), 500


@main_bp.route('/estado-cita/<int:id>', methods=['PUT'])
@permiso_requerido("citas")
def update_estado_cita(id):
    try:
        estado = EstadoCita.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de cita no encontrado"}), 404
            
        data = request.get_json()
        
        if 'nombre' in data:
            nombre = " ".join(data['nombre'].split()).strip()
            existente = EstadoCita.query.filter(
                EstadoCita.nombre.ilike(nombre), 
                EstadoCita.id != id
            ).first()
            if existente:
                return jsonify({"error": "Ya existe otro estado con ese nombre"}), 400
            estado.nombre = nombre
            
        db.session.commit()
        return jsonify({"message": "Estado de cita actualizado", "estado": estado.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar estado de cita: {str(e)}"}), 500


@main_bp.route('/estado-cita/<int:id>', methods=['DELETE'])
@permiso_requerido("citas")
def delete_estado_cita(id):
    try:
        estado = EstadoCita.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de cita no encontrado"}), 404
            
        # Validar que no tenga citas asociadas
        if estado.citas and len(estado.citas) > 0:
            return jsonify({"error": "No se puede eliminar un estado que tiene citas asociadas"}), 400
            
        db.session.delete(estado)
        db.session.commit()
        return jsonify({"message": "Estado de cita eliminado correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar estado de cita: {str(e)}"}), 500
    
# ============================================================
# MÓDULO: NOVEDADES (vacaciones, incapacidades, permisos)
# ============================================================

@main_bp.route('/novedades', methods=['GET'])
@permiso_requerido("empleados")
def get_novedades():
    try:
        novedades = Novedad.query.all()
        return jsonify([n.to_dict() for n in novedades])
    except Exception as e:
        return jsonify({"error": "Error al obtener novedades"}), 500

@main_bp.route('/novedades/empleado/<int:empleado_id>', methods=['GET'])
@permiso_requerido("empleados")
def get_novedades_por_empleado(empleado_id):
    try:
        novedades = Novedad.query.filter_by(empleado_id=empleado_id).all()
        return jsonify([n.to_dict() for n in novedades])
    except Exception as e:
        return jsonify({"error": "Error al obtener novedades"}), 500

@main_bp.route('/novedades', methods=['POST'])
@permiso_requerido("empleados")
def create_novedad():
    try:
        data = request.get_json()
        required = ['empleado_id', 'fecha_inicio', 'fecha_fin', 'tipo']
        for field in required:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Validar empleado
        empleado = Empleado.query.get(data['empleado_id'])
        if not empleado or not empleado.estado:
            return jsonify({"error": "Empleado no existe o está inactivo"}), 400

        # Validar fechas
        try:
            fecha_inicio = datetime.strptime(data['fecha_inicio'], '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(data['fecha_fin'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400

        if fecha_inicio > fecha_fin:
            return jsonify({"error": "La fecha de inicio no puede ser posterior a la fecha de fin."}), 400

        if hora_inicio and hora_fin and hora_fin <= hora_inicio:
            return jsonify({"error": "La hora final debe ser mayor que la hora de inicio."}), 400

        if (hora_inicio and not hora_fin) or (hora_fin and not hora_inicio):
            return jsonify({"error": "Si especifica hora de inicio, también debe especificar hora de fin, y viceversa."}), 400

        # Validar horas si se proporcionan
        hora_inicio = None
        hora_fin = None
        if 'hora_inicio' in data and data['hora_inicio']:
            try:
                hora_inicio = datetime.strptime(data['hora_inicio'], '%H:%M').time()
            except ValueError:
                return jsonify({"error": "Formato de hora inválido. Use HH:MM"}), 400
        if 'hora_fin' in data and data['hora_fin']:
            try:
                hora_fin = datetime.strptime(data['hora_fin'], '%H:%M').time()
            except ValueError:
                return jsonify({"error": "Formato de hora inválido. Use HH:MM"}), 400

        if hora_inicio and hora_fin and hora_fin <= hora_inicio:
            return jsonify({"error": "La hora final debe ser mayor que la hora inicio"}), 400

        # Si se especifica hora pero no la otra, error
        if (hora_inicio and not hora_fin) or (hora_fin and not hora_inicio):
            return jsonify({"error": "Si especifica hora, debe proporcionar ambas (inicio y fin)"}), 400

        novedad = Novedad(
            empleado_id=data['empleado_id'],
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            tipo=data['tipo'],
            motivo=data.get('motivo'),
            activo=data.get('activo', True)
        )
        db.session.add(novedad)
        db.session.commit()
        return jsonify({"message": "Novedad creada", "novedad": novedad.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear novedad: {str(e)}"}), 500

@main_bp.route('/novedades/<int:id>', methods=['PUT'])
@permiso_requerido("empleados")
def update_novedad(id):
    try:
        novedad = Novedad.query.get(id)
        if not novedad:
            return jsonify({"error": "Novedad no encontrada"}), 404

        data = request.get_json()
        # Actualizar campos
        if 'empleado_id' in data:
            empleado = Empleado.query.get(data['empleado_id'])
            if not empleado or not empleado.estado:
                return jsonify({"error": "Empleado no válido o inactivo"}), 400
            novedad.empleado_id = data['empleado_id']
        if 'fecha_inicio' in data:
            try:
                novedad.fecha_inicio = datetime.strptime(data['fecha_inicio'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido"}), 400
        if 'fecha_fin' in data:
            try:
                novedad.fecha_fin = datetime.strptime(data['fecha_fin'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido"}), 400
        if 'hora_inicio' in data:
            if data['hora_inicio']:
                try:
                    novedad.hora_inicio = datetime.strptime(data['hora_inicio'], '%H:%M').time()
                except ValueError:
                    return jsonify({"error": "Formato de hora inválido"}), 400
            else:
                novedad.hora_inicio = None
        if 'hora_fin' in data:
            if data['hora_fin']:
                try:
                    novedad.hora_fin = datetime.strptime(data['hora_fin'], '%H:%M').time()
                except ValueError:
                    return jsonify({"error": "Formato de hora inválido"}), 400
            else:
                novedad.hora_fin = None
        if 'tipo' in data:
            novedad.tipo = data['tipo']
        if 'motivo' in data:
            novedad.motivo = data['motivo']
        if 'activo' in data:
            novedad.activo = data['activo']

        # Validar consistencia
        if novedad.fecha_inicio > novedad.fecha_fin:
            return jsonify({"error": "La fecha inicio no puede ser mayor a fecha fin"}), 400
        if novedad.hora_inicio and novedad.hora_fin and novedad.hora_fin <= novedad.hora_inicio:
            return jsonify({"error": "La hora final debe ser mayor que la hora inicio"}), 400
        if (novedad.hora_inicio and not novedad.hora_fin) or (novedad.hora_fin and not novedad.hora_inicio):
            return jsonify({"error": "Si especifica hora, debe proporcionar ambas"}), 400

        db.session.commit()
        return jsonify({"message": "Novedad actualizada", "novedad": novedad.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar novedad: {str(e)}"}), 500

@main_bp.route('/novedades/<int:id>', methods=['DELETE'])
@permiso_requerido("empleados")
def delete_novedad(id):
    try:
        novedad = Novedad.query.get(id)
        if not novedad:
            return jsonify({"error": "Novedad no encontrada"}), 404
        db.session.delete(novedad)
        db.session.commit()
        return jsonify({"message": "Novedad eliminada correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar novedad: {str(e)}"}), 500