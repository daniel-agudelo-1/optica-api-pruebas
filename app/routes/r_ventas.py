from flask import jsonify, request
from app.database import db
from app.Models.models import Venta, DetalleVenta, Abono, Producto, Cliente, EstadoVenta
from datetime import datetime
from app.routes import main_bp
from app.auth.decorators import permiso_requerido


# ============================================================
# MÓDULO: VENTAS
# ============================================================

@main_bp.route('/ventas', methods=['GET'])
@permiso_requerido("ventas")
def get_ventas():
    try:
        ventas = Venta.query.order_by(Venta.fecha_venta.desc()).all()
        return jsonify([venta.to_dict() for venta in ventas])
    except Exception as e:
        return jsonify({"error": f"Error al obtener ventas: {str(e)}"}), 500


@main_bp.route('/ventas', methods=['POST'])
@permiso_requerido("ventas")
def create_venta():
    # Ya no se permiten ventas directas. Solo desde pedidos.
    return jsonify({
        "error": "No se permite crear ventas directamente. Las ventas se generan automáticamente al marcar un pedido como 'entregado' estando pagado al 100%."
    }), 400


@main_bp.route('/ventas/<int:id>', methods=['GET'])
@permiso_requerido("ventas")
def get_venta(id):
    try:
        venta = Venta.query.get(id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404
        return jsonify(venta.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error al obtener venta: {str(e)}"}), 500


@main_bp.route('/ventas/<int:id>', methods=['PUT'])
@permiso_requerido("ventas")
def update_venta(id):
    try:
        venta = Venta.query.get(id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404
        
        data = request.get_json()
        
        if 'estado_id' in data:
            nuevo_estado_id = data['estado_id']
            nuevo_estado = EstadoVenta.query.get(nuevo_estado_id)
            if not nuevo_estado:
                return jsonify({"error": "Estado inválido"}), 400
            
            if nuevo_estado.nombre not in ['completada', 'cancelada']:
                return jsonify({"error": "Solo se puede cambiar a 'completada' o 'cancelada'"}), 400
            
            if nuevo_estado.nombre == 'cancelada' and venta.estado_venta.nombre != 'cancelada':
                # Restaurar stock solo para detalles que sean productos (no servicios)
                for detalle in venta.detalles:
                    if detalle.producto_id:   # ← solo si es producto
                        producto = Producto.query.get(detalle.producto_id)
                        if producto:
                            producto.stock += detalle.cantidad
            
            venta.estado_id = nuevo_estado_id
        
        # No permitir modificar otros campos
        if 'total' in data:
            return jsonify({"error": "No se puede modificar el total directamente."}), 400
        if 'metodo_pago' in data:
            return jsonify({"error": "No se puede modificar el método de pago de una venta existente."}), 400
        if 'metodo_entrega' in data:
            return jsonify({"error": "No se puede modificar el método de entrega de una venta existente."}), 400
        if 'direccion_entrega' in data:
            return jsonify({"error": "No se puede modificar la dirección de una venta existente."}), 400
        if 'transferencia_comprobante' in data:
            return jsonify({"error": "No se puede modificar el comprobante de una venta existente."}), 400
        
        db.session.commit()
        return jsonify({"message": "Venta actualizada", "venta": venta.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar venta: {str(e)}"}), 500


@main_bp.route('/ventas/<int:id>', methods=['DELETE'])
@permiso_requerido("ventas")
def delete_venta(id):
    try:
        venta = Venta.query.get(id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404
        
        if venta.abonos and len(venta.abonos) > 0:
            return jsonify({"error": "No se puede eliminar una venta con abonos registrados"}), 400
        
        if venta.estado_venta.nombre != 'cancelada':
            for detalle in venta.detalles:
                if detalle.producto_id:   # ← solo productos
                    producto = Producto.query.get(detalle.producto_id)
                    if producto:
                        producto.stock += detalle.cantidad
        
        db.session.delete(venta)
        db.session.commit()
        return jsonify({"message": "Venta eliminada correctamente y stock restaurado"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar venta: {str(e)}"}), 500


@main_bp.route('/ventas/<int:venta_id>/detalles', methods=['GET'])
@permiso_requerido("ventas")
def get_detalles_venta_especifica(venta_id):
    try:
        venta = Venta.query.get(venta_id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404
            
        detalles = DetalleVenta.query.filter_by(venta_id=venta_id).all()
        return jsonify([detalle.to_dict() for detalle in detalles])
        
    except Exception as e:
        return jsonify({"error": f"Error al obtener detalles de la venta: {str(e)}"}), 500


# ============================================================
# MÓDULO: TABLAS MAESTRAS - ESTADO VENTA
# ============================================================

@main_bp.route('/estado-venta', methods=['GET'])
@permiso_requerido("ventas")
def get_estados_venta():
    try:
        estados = EstadoVenta.query.all()
        return jsonify([estado.to_dict() for estado in estados])
    except Exception as e:
        return jsonify({"error": "Error al obtener estados de venta"}), 500

@main_bp.route('/estado-venta', methods=['POST'])
@permiso_requerido("ventas")
def create_estado_venta():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400

        estado = EstadoVenta(nombre=data['nombre'])
        db.session.add(estado)
        db.session.commit()
        return jsonify({"message": "Estado de venta creado", "estado": estado.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear estado de venta"}), 500

@main_bp.route('/estado-venta/<int:id>', methods=['PUT'])
@permiso_requerido("ventas")
def update_estado_venta(id):
    try:
        estado = EstadoVenta.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de venta no encontrado"}), 404

        data = request.get_json()
        if 'nombre' in data:
            estado.nombre = data['nombre']

        db.session.commit()
        return jsonify({"message": "Estado de venta actualizado", "estado": estado.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar estado de venta"}), 500

@main_bp.route('/estado-venta/<int:id>', methods=['DELETE'])
@permiso_requerido("ventas")
def delete_estado_venta(id):
    try:
        estado = EstadoVenta.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de venta no encontrado"}), 404

        # Verificar que no haya ventas usando este estado
        if Venta.query.filter_by(estado_id=id).first():
            return jsonify({"error": "No se puede eliminar un estado que está siendo usado por ventas"}), 400

        db.session.delete(estado)
        db.session.commit()
        return jsonify({"message": "Estado de venta eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar estado de venta"}), 500

# ============================================================
# MÓDULO: ABONOS
# ============================================================

@main_bp.route('/ventas/<int:venta_id>/abonos', methods=['POST'])
@permiso_requerido("ventas")
def add_abono(venta_id):
    return jsonify({"error": "No se permiten abonos directos sobre ventas. Registre abonos en el pedido correspondiente."}), 400

@main_bp.route('/ventas/<int:venta_id>/abonos', methods=['GET'])
@permiso_requerido("ventas")
def get_abonos(venta_id):
    return jsonify({"error": "Los abonos de una venta se pueden consultar a través del endpoint GET /ventas/<id>"}), 400

@main_bp.route('/abonos/<int:id>', methods=['DELETE'])
@permiso_requerido("ventas")
def delete_abono(id):
    try:
        abono = Abono.query.get(id)
        if not abono:
            return jsonify({"error": "Abono no encontrado"}), 404
        
        # Si el abono pertenece a una venta, verificar que no esté cancelada
        if abono.venta_id:
            venta = Venta.query.get(abono.venta_id)
            if venta and venta.estado_venta.nombre == 'cancelada':
                return jsonify({"error": "No se puede eliminar un abono de una venta cancelada"}), 400
        
        db.session.delete(abono)
        db.session.commit()
        return jsonify({"message": "Abono eliminado correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar abono: {str(e)}"}), 500

# ============================================================
# MÓDULO: DETALLES DE VENTA
# ============================================================

@main_bp.route('/detalle-venta', methods=['GET'])
@permiso_requerido("ventas")
def get_detalles_venta():
    try:
        detalles = DetalleVenta.query.all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": f"Error al obtener detalles de venta: {str(e)}"}), 500


@main_bp.route('/detalle-venta', methods=['POST'])
@permiso_requerido("ventas")
def create_detalle_venta():
    return jsonify({"error": "No se pueden crear detalles de venta manualmente. Se crean automáticamente desde el pedido."}), 400


@main_bp.route('/detalle-venta/<int:id>', methods=['PUT'])
@permiso_requerido("ventas")
def update_detalle_venta(id):
    try:
        detalle = DetalleVenta.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de venta no encontrado"}), 404
        
        venta = Venta.query.get(detalle.venta_id)
        if not venta:
            return jsonify({"error": "La venta asociada no existe"}), 404
        if venta.estado_venta.nombre == 'cancelada':
            return jsonify({"error": "No se puede modificar una venta cancelada"}), 400
        
        data = request.get_json()
        
        # No permitir cambio de producto ni de servicio
        if 'producto_id' in data or 'servicio_id' in data:
            return jsonify({"error": "No se puede cambiar el producto o servicio de un detalle existente. Elimine el detalle y créelo de nuevo."}), 400
        
        old_subtotal = detalle.subtotal
        old_cantidad = detalle.cantidad
        
        # Actualizar cantidad
        if 'cantidad' in data:
            try:
                nueva_cantidad = int(data['cantidad'])
            except (ValueError, TypeError):
                return jsonify({"error": "La cantidad debe ser un número válido"}), 400
            
            if nueva_cantidad <= 0:
                return jsonify({"error": "La cantidad debe ser mayor a 0"}), 400
            
            # Ajustar stock solo si es producto
            if detalle.producto_id:
                producto = Producto.query.get(detalle.producto_id)
                if producto:
                    producto.stock += old_cantidad
                    if producto.stock < nueva_cantidad:
                        return jsonify({"error": f"Stock insuficiente para '{producto.nombre}'"}), 400
                    producto.stock -= nueva_cantidad
            
            detalle.cantidad = nueva_cantidad
        
        # Actualizar precio unitario
        if 'precio_unitario' in data:
            try:
                nuevo_precio = float(data['precio_unitario'])
            except (ValueError, TypeError):
                return jsonify({"error": "El precio debe ser un número válido"}), 400
            
            if nuevo_precio <= 0:
                return jsonify({"error": "El precio unitario debe ser mayor a 0"}), 400
            detalle.precio_unitario = nuevo_precio
        
        # Actualizar descuento
        if 'descuento' in data:
            nuevo_descuento = float(data['descuento'])
            if nuevo_descuento < 0:
                return jsonify({"error": "El descuento no puede ser negativo"}), 400
            detalle.descuento = nuevo_descuento
        
        # Recalcular subtotal
        detalle.subtotal = (detalle.cantidad * detalle.precio_unitario) - detalle.descuento
        if detalle.subtotal < 0:
            return jsonify({"error": "El subtotal no puede ser negativo"}), 400
        
        # Actualizar total de la venta
        venta.total = venta.total - old_subtotal + detalle.subtotal
        
        db.session.commit()
        return jsonify({"message": "Detalle de venta actualizado", "detalle": detalle.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar detalle de venta: {str(e)}"}), 500


@main_bp.route('/detalle-venta/<int:id>', methods=['DELETE'])
@permiso_requerido("ventas")
def delete_detalle_venta(id):
    try:
        detalle = DetalleVenta.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de venta no encontrado"}), 404
        
        venta = Venta.query.get(detalle.venta_id)
        if not venta:
            return jsonify({"error": "La venta asociada no existe"}), 404
        if venta.estado_venta.nombre == 'cancelada':
            return jsonify({"error": "No se puede modificar una venta cancelada"}), 400
        
        # Revertir stock solo si es producto
        if detalle.producto_id:
            producto = Producto.query.get(detalle.producto_id)
            if producto:
                producto.stock += detalle.cantidad
        
        # Actualizar total de la venta
        venta.total -= detalle.subtotal
        
        db.session.delete(detalle)
        db.session.commit()
        
        return jsonify({"message": "Detalle de venta eliminado correctamente y stock restaurado (si aplica)"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar detalle de venta: {str(e)}"}), 500