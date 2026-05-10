from flask import jsonify, request
from app.database import db
from app.Models.models import CampanaSalud, EstadoCita, Empleado, Horario, Novedad, Cita
from datetime import datetime, timedelta
from app.routes import main_bp
from app.auth.decorators import permiso_requerido

# ============================================================
# FUNCIÓN AUXILIAR: VALIDAR DISPONIBILIDAD DE EMPLEADO
# ============================================================
def validar_disponibilidad_empleado(empleado_id, fecha, hora, duracion=60, exclude_campana_id=None):
    """
    Verifica si un empleado está disponible en una fecha y hora específicas.
    - Valida novedades (día completo o rango horario)
    - Valida horario laboral
    - Valida citas existentes
    - Valida otras campañas de salud del mismo empleado (opcional exclude)
    Retorna {"disponible": bool, "mensaje": str}
    """
    # 1. Verificar novedades
    novedad = Novedad.query.filter(
        Novedad.empleado_id == empleado_id,
        Novedad.fecha_inicio <= fecha,
        Novedad.fecha_fin >= fecha,
        Novedad.activo == True
    ).first()
    if novedad:
        if novedad.hora_inicio is None and novedad.hora_fin is None:
            return {"disponible": False, "mensaje": "El empleado no está disponible (novedad todo el día)"}
        if novedad.hora_inicio and novedad.hora_fin:
            if novedad.hora_inicio <= hora <= novedad.hora_fin:
                return {"disponible": False, "mensaje": "El empleado no está disponible en ese horario por novedad"}
    
    # 2. Verificar horario laboral
    dia_semana = fecha.weekday()
    horario = Horario.query.filter_by(empleado_id=empleado_id, dia=dia_semana, activo=True).first()
    if not horario:
        return {"disponible": False, "mensaje": "El empleado no tiene horario configurado para este día"}
    if not (horario.hora_inicio <= hora <= horario.hora_final):
        return {"disponible": False, "mensaje": f"El empleado solo trabaja de {horario.hora_inicio.strftime('%H:%M')} a {horario.hora_final.strftime('%H:%M')}"}
    
    # 3. Verificar solapamiento con citas
    inicio_solicitado = datetime.combine(fecha, hora)
    fin_solicitado = inicio_solicitado + timedelta(minutes=duracion)
    citas = Cita.query.filter(Cita.empleado_id == empleado_id, Cita.fecha == fecha).all()
    for cita in citas:
        inicio_cita = datetime.combine(cita.fecha, cita.hora)
        fin_cita = inicio_cita + timedelta(minutes=cita.duracion or 30)
        if inicio_solicitado < fin_cita and fin_solicitado > inicio_cita:
            return {"disponible": False, "mensaje": "El empleado ya tiene una cita en ese horario"}
    
    # 4. Verificar solapamiento con otras campañas del mismo empleado
    campanas_query = CampanaSalud.query.filter(
        CampanaSalud.empleado_id == empleado_id,
        CampanaSalud.fecha == fecha,
        CampanaSalud.hora == hora
    )
    if exclude_campana_id:
        campanas_query = campanas_query.filter(CampanaSalud.id != exclude_campana_id)
    if campanas_query.first():
        return {"disponible": False, "mensaje": "El empleado ya tiene otra campaña de salud en ese mismo horario"}
    
    return {"disponible": True, "mensaje": "Disponible"}


# ============================================================
# MÓDULO: CAMPAÑAS DE SALUD (CRUD completo con validaciones)
# ============================================================

@main_bp.route('/campanas-salud', methods=['GET'])
@permiso_requerido("citas")
def get_campanas_salud():
    try:
        campanas = CampanaSalud.query.order_by(
            CampanaSalud.fecha.desc(), 
            CampanaSalud.hora.desc()
        ).all()
        return jsonify([campana.to_dict() for campana in campanas])
    except Exception as e:
        return jsonify({"error": f"Error al obtener campañas: {str(e)}"}), 500


@main_bp.route('/campanas-salud/<int:id>', methods=['GET'])
@permiso_requerido("citas")
def get_campana_salud(id):
    try:
        campana = CampanaSalud.query.get(id)
        if not campana:
            return jsonify({"error": "Campaña no encontrada"}), 404
        return jsonify(campana.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error al obtener campaña: {str(e)}"}), 500


@main_bp.route('/campanas-salud', methods=['POST'])
@permiso_requerido("citas")
def create_campana_salud():
    try:
        data = request.get_json()
        
        # Campos obligatorios
        required_fields = ['empleado_id', 'empresa', 'nit_empresa', 'fecha', 'hora']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"El campo '{field}' es requerido"}), 400
        
        # Validar empleado (existe y activo)
        empleado = Empleado.query.get(data['empleado_id'])
        if not empleado:
            return jsonify({"error": "El empleado especificado no existe"}), 404
        if hasattr(empleado, 'estado') and not empleado.estado:
            return jsonify({"error": "No se puede asignar una campaña a un empleado inactivo"}), 400
        
        # ❌ VALIDACIÓN DE NIT ÚNICO ELIMINADA
        # nit = data['nit_empresa'].strip()
        # if CampanaSalud.query.filter_by(nit_empresa=nit).first():
        #     return jsonify({"error": "Ya existe una campaña con ese NIT de empresa"}), 400
        
        # Validar empresa no vacía
        empresa = data['empresa'].strip()
        if not empresa:
            return jsonify({"error": "El nombre de la empresa es obligatorio"}), 400
        
        # Validar formato de fecha y hora
        try:
            fecha = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
            hora = datetime.strptime(data['hora'], '%H:%M').time()
        except ValueError:
            return jsonify({"error": "Formato inválido. Use YYYY-MM-DD para fecha y HH:MM para hora"}), 400
        
        # Validar que no sea en el pasado
        if fecha < datetime.now().date():
            return jsonify({"error": "No se pueden crear campañas en fechas pasadas"}), 400
        
        # ✅ Validar solapamiento por empresa (misma empresa, misma fecha y hora) - OPCIONAL, mantener o comentar
        conflicto_empresa = CampanaSalud.query.filter(
            CampanaSalud.empresa == empresa,
            CampanaSalud.fecha == fecha,
            CampanaSalud.hora == hora
        ).first()
        if conflicto_empresa:
            return jsonify({"error": "La empresa ya tiene una campaña agendada en esa fecha y hora"}), 400
        
        # Validar disponibilidad del empleado (incluye solapamiento por empleado)
        disponibilidad = validar_disponibilidad_empleado(data['empleado_id'], fecha, hora, duracion=60)
        if not disponibilidad['disponible']:
            return jsonify({"error": disponibilidad['mensaje']}), 400
        
        # Validar estado (opcional, por defecto 2 = Pendiente)
        estado_cita_id = data.get('estado_cita_id', 2)
        estado_cita = EstadoCita.query.get(estado_cita_id)
        if not estado_cita:
            return jsonify({"error": "El estado de cita especificado no existe"}), 400
        
        # Crear campaña
        campana = CampanaSalud(
            empleado_id=data['empleado_id'],
            empresa=empresa,
            nit_empresa=data['nit_empresa'].strip(),
            contacto=data.get('contacto', '').strip(),
            fecha=fecha,
            hora=hora,
            direccion=data.get('direccion', '').strip(),
            observaciones=data.get('observaciones', '').strip(),
            descripcion=data.get('descripcion', '').strip(),
            estado_cita_id=estado_cita_id
        )
        
        db.session.add(campana)
        db.session.commit()
        return jsonify({"message": "Campaña creada", "campana": campana.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear campaña: {str(e)}"}), 500


@main_bp.route('/campanas-salud/<int:id>', methods=['PUT'])
@permiso_requerido("citas")
def update_campana_salud(id):
    try:
        campana = CampanaSalud.query.get(id)
        if not campana:
            return jsonify({"error": "Campaña no encontrada"}), 404
        
        data = request.get_json()
        
        # Actualizar empleado (con validaciones)
        if 'empleado_id' in data:
            nuevo_empleado = Empleado.query.get(data['empleado_id'])
            if not nuevo_empleado:
                return jsonify({"error": "El empleado especificado no existe"}), 404
            if hasattr(nuevo_empleado, 'estado') and not nuevo_empleado.estado:
                return jsonify({"error": "No se puede asignar una campaña a un empleado inactivo"}), 400
            campana.empleado_id = data['empleado_id']
        
        # Actualizar empresa
        if 'empresa' in data:
            empresa = data['empresa'].strip()
            if not empresa:
                return jsonify({"error": "El nombre de la empresa no puede estar vacío"}), 400
            campana.empresa = empresa
        
        # ❌ ACTUALIZAR NIT SIN VALIDACIÓN DE UNICIDAD
        if 'nit_empresa' in data:
            nit = data['nit_empresa'].strip()
            if not nit:
                return jsonify({"error": "El NIT de la empresa no puede estar vacío"}), 400
            # Se asigna directamente sin verificar duplicados
            campana.nit_empresa = nit
        
        # Actualizar contacto
        if 'contacto' in data:
            campana.contacto = data['contacto'].strip() if data['contacto'] else None
        
        # Actualizar fecha
        if 'fecha' in data:
            try:
                nueva_fecha = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
                if nueva_fecha < datetime.now().date():
                    return jsonify({"error": "No se puede reprogramar a una fecha pasada"}), 400
                campana.fecha = nueva_fecha
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido (use YYYY-MM-DD)"}), 400
        
        # Actualizar hora
        if 'hora' in data:
            try:
                campana.hora = datetime.strptime(data['hora'], '%H:%M').time()
            except ValueError:
                return jsonify({"error": "Formato de hora inválido (use HH:MM)"}), 400
        
        # Actualizar dirección
        if 'direccion' in data:
            campana.direccion = data['direccion'].strip() if data['direccion'] else None
        
        # Actualizar observaciones
        if 'observaciones' in data:
            campana.observaciones = data['observaciones'].strip() if data['observaciones'] else None
        
        # Actualizar descripción
        if 'descripcion' in data:
            campana.descripcion = data['descripcion'].strip() if data['descripcion'] else None
        
        # Actualizar estado
        if 'estado_cita_id' in data:
            estado = EstadoCita.query.get(data['estado_cita_id'])
            if not estado:
                return jsonify({"error": "Estado de cita inválido"}), 400
            campana.estado_cita_id = data['estado_cita_id']
        
        # --- Validaciones de disponibilidad (si cambió empleado, fecha u hora) ---
        if 'empleado_id' in data or 'fecha' in data or 'hora' in data:
            disponibilidad = validar_disponibilidad_empleado(
                campana.empleado_id,
                campana.fecha,
                campana.hora,
                duracion=60,
                exclude_campana_id=campana.id
            )
            if not disponibilidad['disponible']:
                return jsonify({"error": disponibilidad['mensaje']}), 400
        
        # ✅ Validar solapamiento por empresa (si cambió empresa, fecha u hora) - OPCIONAL
        if 'empresa' in data or 'fecha' in data or 'hora' in data:
            conflicto_empresa = CampanaSalud.query.filter(
                CampanaSalud.empresa == campana.empresa,
                CampanaSalud.fecha == campana.fecha,
                CampanaSalud.hora == campana.hora,
                CampanaSalud.id != campana.id
            ).first()
            if conflicto_empresa:
                return jsonify({"error": "La empresa ya tiene otra campaña en esa fecha y hora"}), 400
        
        db.session.commit()
        return jsonify({"message": "Campaña actualizada", "campana": campana.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar campaña: {str(e)}"}), 500


@main_bp.route('/campanas-salud/<int:id>', methods=['DELETE'])
@permiso_requerido("citas")
def delete_campana_salud(id):
    try:
        campana = CampanaSalud.query.get(id)
        if not campana:
            return jsonify({"error": "Campaña no encontrada"}), 404
        
        # No permitir eliminar campañas completadas
        if campana.estado_cita_id:
            estado = EstadoCita.query.get(campana.estado_cita_id)
            if estado and estado.nombre.lower() == 'completada':
                return jsonify({"error": "No se puede eliminar una campaña que ya está completada"}), 400
        
        db.session.delete(campana)
        db.session.commit()
        return jsonify({"message": "Campaña eliminada correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar campaña: {str(e)}"}), 500


@main_bp.route('/empleados/<int:empleado_id>/campanas', methods=['GET'])
@permiso_requerido("citas")
def get_campanas_por_empleado(empleado_id):
    try:
        empleado = Empleado.query.get(empleado_id)
        if not empleado:
            return jsonify({"error": "Empleado no encontrado"}), 404

        campanas = CampanaSalud.query.filter_by(empleado_id=empleado_id)\
            .order_by(CampanaSalud.fecha.desc(), CampanaSalud.hora.desc()).all()
        return jsonify([campana.to_dict() for campana in campanas])
    except Exception as e:
        return jsonify({"error": f"Error al obtener campañas del empleado: {str(e)}"}), 500