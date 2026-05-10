from flask import jsonify, request
from app.database import db
from app.Models.models import Pedido, DetallePedido, Venta, DetalleVenta, Producto, Cliente, Abono, EstadoPedido
from datetime import datetime
from app.routes import main_bp
from app.auth.decorators import permiso_requerido

# ============================================================
# MÓDULO: PEDIDOS
# ============================================================

@main_bp.route('/pedidos', methods=['GET'])
@permiso_requerido("pedidos")
def get_pedidos():
    try:
        pedidos = Pedido.query.order_by(Pedido.fecha.desc()).all()
        return jsonify([pedido.to_dict() for pedido in pedidos])
    except Exception as e:
        return jsonify({"error": f"Error al obtener pedidos: {str(e)}"}), 500


@main_bp.route('/pedidos', methods=['POST'])
@permiso_requerido("pedidos")
def create_pedido():
    try:
        data = request.get_json()
        
        # 1. Validar campos requeridos
        required_fields = ['cliente_id', 'metodo_pago', 'items']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"El campo '{field}' es requerido"}), 400
        
        # 2. Validar cliente
        cliente = Cliente.query.get(data['cliente_id'])
        if not cliente:
            return jsonify({"error": "El cliente especificado no existe"}), 404
        if not cliente.estado:
            return jsonify({"error": "No se puede crear un pedido para un cliente inactivo"}), 400
        
        # 3. Validar método de pago
        metodo_pago = data['metodo_pago']
        if metodo_pago not in ['efectivo', 'transferencia', 'tarjeta']:
            return jsonify({"error": "Método de pago inválido. Opciones: efectivo, transferencia, tarjeta"}), 400
        
        # 4. Validar método de entrega
        metodo_entrega = data.get('metodo_entrega')
        if metodo_entrega and metodo_entrega not in ['tienda', 'domicilio']:
            return jsonify({"error": "Método de entrega inválido. Opciones: tienda, domicilio"}), 400
        
        # 5. Validar dirección de entrega si es domicilio
        if metodo_entrega == 'domicilio' and not data.get('direccion_entrega'):
            return jsonify({"error": "Para envío a domicilio, la dirección de entrega es requerida"}), 400
        
        # 6. Validar items
        items = data['items']
        if not isinstance(items, list) or len(items) == 0:
            return jsonify({"error": "El pedido debe tener al menos un item"}), 400
        
        # Obtener ID del estado "pendiente" (asumiendo id=1, puedes buscarlo por nombre)
        estado_pendiente = EstadoPedido.query.filter_by(nombre='pendiente').first()
        if not estado_pendiente:
            return jsonify({"error": "Estado 'pendiente' no encontrado en la base de datos"}), 500
        
        # Crear pedido usando estado_id en lugar de string
        pedido = Pedido(
            cliente_id=data['cliente_id'],
            metodo_pago=metodo_pago,
            metodo_entrega=metodo_entrega,
            direccion_entrega=data.get('direccion_entrega', '').strip(),
            # Nuevos campos de dirección
            departamento_entrega=data.get('departamento_entrega', '').strip(),
            municipio_entrega=data.get('municipio_entrega', '').strip(),
            barrio_entrega=data.get('barrio_entrega', '').strip(),
            codigo_postal_entrega=data.get('codigo_postal_entrega', '').strip(),
            estado_id=estado_pendiente.id,
            transferencia_comprobante=data.get('transferencia_comprobante'),
            total=0,
            abono_acumulado=0
        )
        
        db.session.add(pedido)
        db.session.flush()
        
        total_calculado = 0
        productos_procesados = []
        
        # 7. Procesar cada item
        for idx, item_data in enumerate(items):
            if 'producto_id' not in item_data:
                db.session.rollback()
                return jsonify({"error": f"El item {idx+1} no tiene 'producto_id'"}), 400
            if 'cantidad' not in item_data:
                db.session.rollback()
                return jsonify({"error": f"El item {idx+1} no tiene 'cantidad'"}), 400
            
            producto = Producto.query.get(item_data['producto_id'])
            if not producto:
                db.session.rollback()
                return jsonify({"error": f"El producto con ID {item_data['producto_id']} no existe"}), 404
            if not producto.estado:
                db.session.rollback()
                return jsonify({"error": f"El producto '{producto.nombre}' está inactivo"}), 400
            
            try:
                cantidad = int(item_data['cantidad'])
            except (ValueError, TypeError):
                db.session.rollback()
                return jsonify({"error": f"La cantidad del item {idx+1} debe ser un número válido"}), 400
            
            if cantidad <= 0:
                db.session.rollback()
                return jsonify({"error": f"La cantidad del item {idx+1} debe ser mayor a 0"}), 400
            
            if producto.stock < cantidad:
                db.session.rollback()
                return jsonify({
                    "error": f"Stock insuficiente para '{producto.nombre}'. Disponible: {producto.stock}, solicitado: {cantidad}"
                }), 400
            
            precio = float(item_data.get('precio_unitario', producto.precio_venta))
            if precio <= 0:
                db.session.rollback()
                return jsonify({"error": f"El precio unitario del item {idx+1} debe ser mayor a 0"}), 400
            
            subtotal = cantidad * precio
            total_calculado += subtotal
            
            producto.stock -= cantidad
            productos_procesados.append(producto)
            
            detalle = DetallePedido(
                pedido_id=pedido.id,
                producto_id=producto.id,
                cantidad=cantidad,
                precio_unitario=precio,
                subtotal=subtotal
            )
            db.session.add(detalle)
        
        pedido.total = total_calculado
        db.session.commit()
        
        return jsonify({"message": "Pedido creado exitosamente", "pedido": pedido.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear pedido: {str(e)}"}), 500


@main_bp.route('/pedidos/<int:id>', methods=['GET'])
@permiso_requerido("pedidos")
def get_pedido(id):
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
        return jsonify(pedido.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error al obtener pedido: {str(e)}"}), 500


@main_bp.route('/pedidos/<int:id>', methods=['PUT'])
@permiso_requerido("pedidos")
def update_pedido(id):
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
        
        data = request.get_json()
        estado_anterior_id = pedido.estado_id
        
        # Obtener nuevo estado_id (puede venir como ID o como nombre)
        nuevo_estado_id = data.get('estado_id')
        if not nuevo_estado_id and 'estado' in data:
            estado_nombre = data['estado']
            estado_obj = EstadoPedido.query.filter_by(nombre=estado_nombre).first()
            if not estado_obj:
                return jsonify({"error": f"Estado '{estado_nombre}' no existe"}), 400
            nuevo_estado_id = estado_obj.id
        elif not nuevo_estado_id:
            nuevo_estado_id = estado_anterior_id
        
        nuevo_estado_obj = EstadoPedido.query.get(nuevo_estado_id)
        if not nuevo_estado_obj:
            return jsonify({"error": "Estado inválido"}), 400
        
        estado_anterior_nombre = pedido.estado.nombre if pedido.estado else None
        nuevo_estado_nombre = nuevo_estado_obj.nombre

        # ========== TRANSICIÓN A ANULADO ==========
        if nuevo_estado_nombre == 'anulado' and estado_anterior_nombre != 'anulado':
            if estado_anterior_nombre == 'pagado':
                return jsonify({"error": "No se puede anular un pedido ya pagado"}), 400
            for detalle in pedido.items:
                producto = Producto.query.get(detalle.producto_id)
                if producto:
                    producto.stock += detalle.cantidad

        # ========== TRANSICIÓN A PAGADO (crear venta) ==========
        if nuevo_estado_nombre == 'pagado' and estado_anterior_nombre != 'pagado':
            # Evitar doble venta
            if hasattr(pedido, 'venta') and pedido.venta:
                return jsonify({"error": "Este pedido ya generó una venta anteriormente"}), 400
            
            from app.Models.models import EstadoVenta
            estado_completada = EstadoVenta.query.filter_by(nombre='completada').first()
            if not estado_completada:
                return jsonify({"error": "Estado 'completada' no encontrado en EstadoVenta"}), 500
            
            venta = Venta(
                pedido_id=pedido.id,
                cliente_id=pedido.cliente_id,
                fecha_pedido=pedido.fecha,
                fecha_venta=datetime.utcnow(),
                total=pedido.total,
                metodo_pago=pedido.metodo_pago,
                metodo_entrega=pedido.metodo_entrega,
                direccion_entrega=pedido.direccion_entrega,
                transferencia_comprobante=pedido.transferencia_comprobante,
                estado_id=estado_completada.id
            )
            db.session.add(venta)
            db.session.flush()  # Para obtener el id de la venta
            
            # Migrar detalles a DetalleVenta
            for detalle_pedido in pedido.items:
                detalle_venta = DetalleVenta(
                    venta_id=venta.id,
                    producto_id=detalle_pedido.producto_id,
                    cantidad=detalle_pedido.cantidad,
                    precio_unitario=detalle_pedido.precio_unitario,
                    subtotal=detalle_pedido.subtotal,
                    descuento=0
                )
                db.session.add(detalle_venta)
            
            # Migrar abonos del pedido a la venta
            for abono in pedido.abonos:
                abono.pedido_id = None
                abono.venta_id = venta.id
        
        # =========================================

        # Actualizar el estado del pedido
        pedido.estado_id = nuevo_estado_id
        
        # Actualizar otros campos permitidos (sin modificar total)
        if 'transferencia_comprobante' in data:
            pedido.transferencia_comprobante = data['transferencia_comprobante']
        if 'direccion_entrega' in data:
            pedido.direccion_entrega = data['direccion_entrega'].strip()
        if 'departamento_entrega' in data:
            pedido.departamento_entrega = data['departamento_entrega'].strip()
        if 'municipio_entrega' in data:
            pedido.municipio_entrega = data['municipio_entrega'].strip()
        if 'barrio_entrega' in data:
            pedido.barrio_entrega = data['barrio_entrega'].strip()
        if 'codigo_postal_entrega' in data:
            pedido.codigo_postal_entrega = data['codigo_postal_entrega'].strip()
        
        if 'metodo_pago' in data:
            if data['metodo_pago'] not in ['efectivo', 'transferencia', 'tarjeta']:
                return jsonify({"error": "Método de pago inválido"}), 400
            pedido.metodo_pago = data['metodo_pago']
        if 'metodo_entrega' in data:
            if data['metodo_entrega'] not in ['tienda', 'domicilio']:
                return jsonify({"error": "Método de entrega inválido"}), 400
            pedido.metodo_entrega = data['metodo_entrega']
        
        if 'total' in data:
            return jsonify({"error": "No se puede modificar el total directamente. Se calcula automáticamente"}), 400
        
        db.session.commit()
        return jsonify({"message": "Pedido actualizado", "pedido": pedido.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar pedido: {str(e)}"}), 500


@main_bp.route('/pedidos/<int:id>', methods=['DELETE'])
@permiso_requerido("pedidos")
def delete_pedido(id):
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
        
        # Validar que no tenga venta asociada
        venta_asociada = Venta.query.filter_by(pedido_id=id).first()
        if venta_asociada:
            return jsonify({"error": "No se puede eliminar un pedido que ya generó una venta"}), 400
        
        # Validar que no esté entregado
        if pedido.estado.nombre in ['pagado', 'anulado']:
            return jsonify({"error": "No se puede eliminar un pedido pagado o anulado"}), 400
        
        # Revertir stock antes de eliminar
        for detalle in pedido.items:
            producto = Producto.query.get(detalle.producto_id)
            if producto:
                producto.stock += detalle.cantidad
        
        # Eliminar abonos asociados al pedido (usando el modelo unificado Abono)
        Abono.query.filter_by(pedido_id=id).delete()
        
        # Eliminar detalles y pedido
        DetallePedido.query.filter_by(pedido_id=id).delete()
        db.session.delete(pedido)
        db.session.commit()
        
        return jsonify({"message": "Pedido eliminado correctamente y stock restaurado"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar pedido: {str(e)}"}), 500


@main_bp.route('/pedidos/cliente/<int:cliente_id>', methods=['GET'])
@permiso_requerido("pedidos")
def get_pedidos_cliente(cliente_id):
    try:
        cliente = Cliente.query.get(cliente_id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        pedidos = Pedido.query.filter_by(cliente_id=cliente_id)\
            .order_by(Pedido.fecha.desc()).all()
        return jsonify([pedido.to_dict() for pedido in pedidos])
    except Exception as e:
        return jsonify({"error": f"Error al obtener pedidos del cliente: {str(e)}"}), 500

@main_bp.route('/pedidos/<int:pedido_id>/detalles', methods=['GET'])
@permiso_requerido("pedidos")
def get_detalles_de_pedido(pedido_id):
    try:
        pedido = Pedido.query.get(pedido_id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
            
        detalles = DetallePedido.query.filter_by(pedido_id=pedido_id).all()
        return jsonify([detalle.to_dict() for detalle in detalles])
        
    except Exception as e:
        return jsonify({"error": f"Error al obtener detalles del pedido: {str(e)}"}), 500


# ============================================================
# MÓDULO: ABONOS DE PEDIDOS (unificado con Abono)
# ============================================================

@main_bp.route('/pedidos/<int:id>/abonos', methods=['GET'])
@permiso_requerido("pedidos")
def get_abonos_pedido(id):
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
        # Usar la relación 'abonos' definida en Pedido (que apunta a Abono con pedido_id)
        abonos = [abono.to_dict() for abono in pedido.abonos]
        return jsonify(abonos)
    except Exception as e:
        return jsonify({"error": f"Error al obtener abonos: {str(e)}"}), 500


@main_bp.route('/pedidos/<int:id>/abonos', methods=['POST'])
@permiso_requerido("pedidos")
def add_abono_pedido(id):
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404

    # No permitir abonos si el pedido ya está pagado o anulado
        if pedido.estado.nombre in ['pagado', 'anulado']:
            return jsonify({"error": f"No se pueden registrar abonos en un pedido {pedido.estado.nombre}"}), 400

        data = request.get_json()
        monto = data.get('monto_abonado')
        if not monto or float(monto) <= 0:
            return jsonify({"error": "El monto del abono debe ser mayor a 0"}), 400

        monto = float(monto)
        nuevo_acumulado = pedido.abono_acumulado + monto

        if nuevo_acumulado > pedido.total:
            return jsonify({"error": f"El abono excede el total del pedido. Máximo permitido: {pedido.total - pedido.abono_acumulado}"}), 400

        # Registrar el abono en la tabla unificada Abono (sin venta_id)
        abono = Abono(
            pedido_id=pedido.id,
            monto=monto,
            observacion=data.get('observacion', '')
        )
        db.session.add(abono)

        # Actualizar acumulado
        pedido.abono_acumulado = nuevo_acumulado

                # Si el abono completa el pago, cambiar estado a "pagado" automáticamente
        if nuevo_acumulado >= pedido.total:
            estado_pagado = EstadoPedido.query.filter_by(nombre='pagado').first()
            if estado_pagado:
                pedido.estado_id = estado_pagado.id

        # NO se crea venta aquí, aunque se complete el pago. Solo se actualiza el acumulado.
        # La venta se creará únicamente cuando se cambie el estado a 'entregado' vía PUT /pedidos/<id>

        db.session.commit()

        return jsonify({
            "message": "Abono registrado",
            "abono_acumulado": pedido.abono_acumulado,
            "saldo_pendiente": pedido.total - pedido.abono_acumulado
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al registrar abono: {str(e)}"}), 500


# ============================================================
# MÓDULO: DETALLES DE PEDIDO (con prohibición de cambio de producto)
# ============================================================

@main_bp.route('/detalle-pedido', methods=['GET'])
@permiso_requerido("pedidos")
def get_detalles_pedido():
    try:
        pedido_id = request.args.get('pedido_id', type=int)
        if pedido_id:
            pedido = Pedido.query.get(pedido_id)
            if not pedido:
                return jsonify({"error": "Pedido no encontrado"}), 404
            detalles = DetallePedido.query.filter_by(pedido_id=pedido_id).all()
        else:
            detalles = DetallePedido.query.all()
        return jsonify([detalle.to_dict() for detalle in detalles])
        
    except Exception as e:
        return jsonify({"error": f"Error al obtener detalles de pedido: {str(e)}"}), 500


@main_bp.route('/detalle-pedido', methods=['POST'])
@permiso_requerido("pedidos")
def create_detalle_pedido():
    try:
        data = request.get_json()
        required_fields = ['pedido_id', 'producto_id', 'cantidad', 'precio_unitario']
        
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo '{field}' es requerido"}), 400
        
        pedido = Pedido.query.get(data['pedido_id'])
        if not pedido:
            return jsonify({"error": "El pedido especificado no existe"}), 404
        
        # Solo permitir modificar pedidos en estado pendiente o confirmado
        if pedido.estado.nombre != 'pendiente':
            return jsonify({"error": f"No se puede modificar un pedido en estado '{pedido.estado.nombre}'. Solo se pueden modificar pedidos pendientes"}), 400
        
        producto = Producto.query.get(data['producto_id'])
        if not producto:
            return jsonify({"error": "El producto especificado no existe"}), 404
        if not producto.estado:
            return jsonify({"error": "No se puede agregar un producto inactivo"}), 400
        
        try:
            cantidad = int(data['cantidad'])
        except (ValueError, TypeError):
            return jsonify({"error": "La cantidad debe ser un número válido"}), 400
        
        if cantidad <= 0:
            return jsonify({"error": "La cantidad debe ser mayor a 0"}), 400
        
        if producto.stock < cantidad:
            return jsonify({
                "error": f"Stock insuficiente para '{producto.nombre}'. Disponible: {producto.stock}"
            }), 400
        
        try:
            precio = float(data['precio_unitario'])
        except (ValueError, TypeError):
            return jsonify({"error": "El precio unitario debe ser un número válido"}), 400
        
        if precio <= 0:
            return jsonify({"error": "El precio unitario debe ser mayor a 0"}), 400
        
        subtotal = cantidad * precio
        
        producto.stock -= cantidad
        
        detalle = DetallePedido(
            pedido_id=data['pedido_id'],
            producto_id=data['producto_id'],
            cantidad=cantidad,
            precio_unitario=precio,
            subtotal=subtotal
        )
        
        db.session.add(detalle)
        pedido.total += subtotal
        db.session.commit()
        
        return jsonify({"message": "Detalle de pedido creado", "detalle": detalle.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear detalle de pedido: {str(e)}"}), 500


@main_bp.route('/detalle-pedido/<int:id>', methods=['PUT'])
@permiso_requerido("pedidos")
def update_detalle_pedido(id):
    try:
        detalle = DetallePedido.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de pedido no encontrado"}), 404
        
        pedido = Pedido.query.get(detalle.pedido_id)
        if not pedido:
            return jsonify({"error": "El pedido asociado no existe"}), 404
        
        if pedido.estado.nombre != 'pendiente':
            return jsonify({"error": f"No se puede modificar un pedido en estado '{pedido.estado.nombre}'. Solo se pueden modificar pedidos pendientes"}), 400
        
        data = request.get_json()
        
        # No permitir cambio de producto
        if 'producto_id' in data:
            return jsonify({"error": "No se puede cambiar el producto de un detalle existente. Elimine el detalle y créelo de nuevo."}), 400
        
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
            
            producto_actual = Producto.query.get(detalle.producto_id)
            if producto_actual:
                producto_actual.stock += old_cantidad  # Revertir vieja
                if producto_actual.stock < nueva_cantidad:
                    return jsonify({"error": f"Stock insuficiente para '{producto_actual.nombre}'"}), 400
                producto_actual.stock -= nueva_cantidad  # Aplicar nueva
            
            detalle.cantidad = nueva_cantidad
        
        # Actualizar precio
        if 'precio_unitario' in data:
            try:
                nuevo_precio = float(data['precio_unitario'])
            except (ValueError, TypeError):
                return jsonify({"error": "El precio debe ser un número válido"}), 400
            
            if nuevo_precio <= 0:
                return jsonify({"error": "El precio unitario debe ser mayor a 0"}), 400
            detalle.precio_unitario = nuevo_precio
        
        # Recalcular subtotal
        detalle.subtotal = detalle.cantidad * detalle.precio_unitario
        
        # Actualizar total del pedido
        pedido.total = pedido.total - old_subtotal + detalle.subtotal
        
        db.session.commit()
        return jsonify({"message": "Detalle de pedido actualizado", "detalle": detalle.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar detalle de pedido: {str(e)}"}), 500


@main_bp.route('/detalle-pedido/<int:id>', methods=['DELETE'])
@permiso_requerido("pedidos")
def delete_detalle_pedido(id):
    try:
        detalle = DetallePedido.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de pedido no encontrado"}), 404
        
        pedido = Pedido.query.get(detalle.pedido_id)
        if not pedido:
            return jsonify({"error": "El pedido asociado no existe"}), 404
        
        if pedido.estado.nombre != 'pendiente':
            return jsonify({"error": f"No se puede modificar un pedido en estado '{pedido.estado.nombre}'. Solo se pueden modificar pedidos pendientes"}), 400
        
        producto = Producto.query.get(detalle.producto_id)
        if producto:
            producto.stock += detalle.cantidad
        
        pedido.total -= detalle.subtotal
        
        db.session.delete(detalle)
        db.session.commit()
        
        return jsonify({"message": "Detalle de pedido eliminado correctamente y stock restaurado"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar detalle de pedido: {str(e)}"}), 500
    
# ============================================================
# MÓDULO: TABLAS MAESTRAS - ESTADO PEDIDO
# ============================================================

@main_bp.route('/estado-pedido', methods=['GET'])
@permiso_requerido("pedidos")
def get_estados_pedido():
    try:
        estados = EstadoPedido.query.all()
        return jsonify([estado.to_dict() for estado in estados])
    except Exception as e:
        return jsonify({"error": "Error al obtener estados de pedido"}), 500

@main_bp.route('/estado-pedido', methods=['POST'])
@permiso_requerido("pedidos")
def create_estado_pedido():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400

        estado = EstadoPedido(nombre=data['nombre'])
        db.session.add(estado)
        db.session.commit()
        return jsonify({"message": "Estado de pedido creado", "estado": estado.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear estado de pedido"}), 500

@main_bp.route('/estado-pedido/<int:id>', methods=['PUT'])
@permiso_requerido("pedidos")
def update_estado_pedido(id):
    try:
        estado = EstadoPedido.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de pedido no encontrado"}), 404

        data = request.get_json()
        if 'nombre' in data:
            estado.nombre = data['nombre']

        db.session.commit()
        return jsonify({"message": "Estado de pedido actualizado", "estado": estado.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar estado de pedido"}), 500

@main_bp.route('/estado-pedido/<int:id>', methods=['DELETE'])
@permiso_requerido("pedidos")
def delete_estado_pedido(id):
    try:
        estado = EstadoPedido.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de pedido no encontrado"}), 404

        # Verificar que no haya pedidos usando este estado
        from app.Models.models import Pedido
        if Pedido.query.filter_by(estado_id=id).first():
            return jsonify({"error": "No se puede eliminar un estado que está siendo usado por pedidos"}), 400

        db.session.delete(estado)
        db.session.commit()
        return jsonify({"message": "Estado de pedido eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar estado de pedido"}), 500