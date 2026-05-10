from flask import jsonify, request
from app.database import db
from app.Models.models import Compra, DetalleCompra, Producto, Proveedor
from datetime import datetime
from app.routes import main_bp
from app.auth.decorators import permiso_requerido


# ============================================================
# MÓDULO: COMPRAS
# ============================================================

@main_bp.route('/compras', methods=['GET'])
@permiso_requerido("compras")
def get_compras():
    try:
        compras = Compra.query.order_by(Compra.fecha.desc()).all()
        return jsonify([compra.to_dict() for compra in compras])
    except Exception as e:
        return jsonify({"error": f"Error al obtener compras: {str(e)}"}), 500


@main_bp.route('/compras', methods=['POST'])
@permiso_requerido("compras")
def create_compra():
    try:
        data = request.get_json()
        
        # 1. Validar datos básicos
        proveedor_id = data.get('proveedor_id')
        detalles_data = data.get('detalles', [])
        
        if not proveedor_id:
            return jsonify({"error": "El campo 'proveedor_id' es requerido"}), 400
        if not detalles_data:
            return jsonify({"error": "La compra debe tener al menos un detalle (producto)"}), 400
        
        # 2. Validar proveedor
        proveedor = Proveedor.query.get(proveedor_id)
        if not proveedor:
            return jsonify({"error": "El proveedor especificado no existe"}), 404
        if not proveedor.estado:
            return jsonify({"error": "No se puede crear una compra con un proveedor inactivo"}), 400
        
        # 3. Crear la compra
        nueva_compra = Compra(
            proveedor_id=proveedor_id,
            total=0,
            estado_compra=data.get('estado_compra', True),
            fecha=datetime.utcnow()
        )
        db.session.add(nueva_compra)
        db.session.flush()  # Para obtener el ID
        
        total_calculado = 0
        productos_actualizados = []
        
        # 4. Procesar cada detalle
        for idx, item in enumerate(detalles_data):
            prod_id = item.get('producto_id')
            cantidad = item.get('cantidad', 0)
            precio_u = item.get('precio_unidad', 0)
            
            # Validar campos del detalle
            if not prod_id:
                db.session.rollback()
                return jsonify({"error": f"El detalle {idx+1} no tiene 'producto_id'"}), 400
            
            # Validar cantidad y precio
            try:
                cantidad = int(cantidad)
                precio_u = float(precio_u)
            except (ValueError, TypeError):
                db.session.rollback()
                return jsonify({"error": f"El detalle {idx+1}: cantidad y precio deben ser números válidos"}), 400
            
            if cantidad <= 0:
                db.session.rollback()
                return jsonify({"error": f"El detalle {idx+1}: la cantidad debe ser mayor a 0"}), 400
            if precio_u <= 0:
                db.session.rollback()
                return jsonify({"error": f"El detalle {idx+1}: el precio unitario debe ser mayor a 0"}), 400
            
            # Validar producto
            producto = Producto.query.get(prod_id)
            if not producto:
                db.session.rollback()
                return jsonify({"error": f"El producto con ID {prod_id} no existe"}), 404
            
            # Validar que el producto esté activo
            if not producto.estado:
                db.session.rollback()
                return jsonify({"error": f"No se puede comprar el producto '{producto.nombre}' porque está inactivo"}), 400
            
            # Calcular subtotal
            subtotal = cantidad * precio_u
            total_calculado += subtotal
            
            # Crear detalle
            detalle = DetalleCompra(
                compra_id=nueva_compra.id,
                producto_id=prod_id,
                precio_unidad=precio_u,
                cantidad=cantidad,
                subtotal=subtotal
            )
            db.session.add(detalle)
            
            # Actualizar stock del producto
            producto.stock += cantidad
            producto.precio_compra = precio_u  # Actualizar precio de compra
            productos_actualizados.append(producto)
        
        # 5. Actualizar total de la compra
        nueva_compra.total = total_calculado
        db.session.commit()
        
        return jsonify({"message": "Compra creada exitosamente", "compra": nueva_compra.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear compra: {str(e)}"}), 500


@main_bp.route('/compras/<int:id>', methods=['PUT'])
@permiso_requerido("compras")
def update_compra(id):
    try:
        compra = Compra.query.get(id)
        if not compra:
            return jsonify({"error": "Compra no encontrada"}), 404
        
        data = request.get_json()
        
        # Validar proveedor si se cambia
        if 'proveedor_id' in data:
            proveedor = Proveedor.query.get(data['proveedor_id'])
            if not proveedor:
                return jsonify({"error": "El proveedor especificado no existe"}), 404
            if not proveedor.estado:
                return jsonify({"error": "No se puede asignar un proveedor inactivo"}), 400
            compra.proveedor_id = data['proveedor_id']
        
        # Validar total (no puede ser negativo)
        if 'total' in data:
            nuevo_total = float(data['total'])
            if nuevo_total < 0:
                return jsonify({"error": "El total no puede ser negativo"}), 400
            compra.total = nuevo_total
        
        if 'estado_compra' in data:
            compra.estado_compra = data['estado_compra']
        
        db.session.commit()
        return jsonify({"message": "Compra actualizada", "compra": compra.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar compra: {str(e)}"}), 500


@main_bp.route('/compras/<int:id>', methods=['DELETE'])
@permiso_requerido("compras")
def delete_compra(id):
    """
    Eliminar una compra es delicado porque ya alteró el stock.
    Aquí restamos el stock que se había sumado.
    """
    try:
        compra = Compra.query.get(id)
        if not compra:
            return jsonify({"error": "Compra no encontrada"}), 404
        
        # Revertir el stock de cada producto antes de borrar
        for detalle in compra.detalles:
            producto = Producto.query.get(detalle.producto_id)
            if producto:
                # Validar que haya suficiente stock para revertir
                if producto.stock < detalle.cantidad:
                    return jsonify({
                        "error": f"No se puede eliminar la compra: El producto '{producto.nombre}' ya se vendió y no hay suficiente stock para revertir."
                    }), 400
                producto.stock -= detalle.cantidad
        
        db.session.delete(compra)
        db.session.commit()
        return jsonify({"message": "Compra eliminada y stock revertido correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar compra: {str(e)}"}), 500


@main_bp.route('/compras/<int:compra_id>/detalles', methods=['GET'])
@permiso_requerido("compras")
def get_detalles_compra_especifica(compra_id):
    try:
        compra = Compra.query.get(compra_id)
        if not compra:
            return jsonify({"error": "Compra no encontrada"}), 404
            
        detalles = DetalleCompra.query.filter_by(compra_id=compra_id).all()
        return jsonify([detalle.to_dict() for detalle in detalles])
        
    except Exception as e:
        return jsonify({"error": f"Error al obtener detalles de la compra: {str(e)}"}), 500


# ============================================================
# MÓDULO: DETALLES DE COMPRA
# ============================================================

@main_bp.route('/detalle-compra', methods=['GET'])
@permiso_requerido("compras")
def get_detalles_compra():
    try:
        detalles = DetalleCompra.query.all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": "Error al obtener detalles de compra"}), 500


@main_bp.route('/detalle-compra', methods=['POST'])
@permiso_requerido("compras")
def create_detalle_compra():
    try:
        data = request.get_json()
        required_fields = ['compra_id', 'producto_id', 'cantidad', 'precio_unidad']
        
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400
        
        # Validar compra
        compra = Compra.query.get(data['compra_id'])
        if not compra:
            return jsonify({"error": "La compra especificada no existe"}), 404
        
        # Validar producto
        producto = Producto.query.get(data['producto_id'])
        if not producto:
            return jsonify({"error": "El producto especificado no existe"}), 404
        if not producto.estado:
            return jsonify({"error": "No se puede agregar un producto inactivo a la compra"}), 400
        
        # Validar cantidad y precio
        try:
            cantidad = int(data['cantidad'])
            precio_unidad = float(data['precio_unidad'])
        except (ValueError, TypeError):
            return jsonify({"error": "Cantidad y precio deben ser números válidos"}), 400
        
        if cantidad <= 0:
            return jsonify({"error": "La cantidad debe ser mayor a 0"}), 400
        if precio_unidad <= 0:
            return jsonify({"error": "El precio unitario debe ser mayor a 0"}), 400
        
        subtotal = cantidad * precio_unidad
        
        detalle = DetalleCompra(
            compra_id=data['compra_id'],
            producto_id=data['producto_id'],
            cantidad=cantidad,
            precio_unidad=precio_unidad,
            subtotal=subtotal
        )
        
        db.session.add(detalle)
        
        # Actualizar total de la compra y stock del producto
        compra.total += subtotal
        producto.stock += cantidad
        
        db.session.commit()
        return jsonify({"message": "Detalle de compra creado", "detalle": detalle.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear detalle de compra: {str(e)}"}), 500


@main_bp.route('/detalle-compra/<int:id>', methods=['PUT'])
@permiso_requerido("compras")
def update_detalle_compra(id):
    try:
        detalle = DetalleCompra.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de compra no encontrado"}), 404
        
        data = request.get_json()
        compra = Compra.query.get(detalle.compra_id)
        
        # Guardar valores antiguos para recalcular
        old_cantidad = detalle.cantidad
        old_precio = detalle.precio_unidad
        old_subtotal = detalle.subtotal
        
        # Validar y actualizar compra_id
        if 'compra_id' in data:
            nueva_compra = Compra.query.get(data['compra_id'])
            if not nueva_compra:
                return jsonify({"error": "La compra especificada no existe"}), 404
            detalle.compra_id = data['compra_id']
            compra = nueva_compra
        
        # Validar y actualizar producto
        if 'producto_id' in data:
            producto = Producto.query.get(data['producto_id'])
            if not producto:
                return jsonify({"error": "El producto especificado no existe"}), 404
            if not producto.estado:
                return jsonify({"error": "No se puede asignar un producto inactivo"}), 400
            detalle.producto_id = data['producto_id']
        
        # Actualizar cantidad
        if 'cantidad' in data:
            try:
                nueva_cantidad = int(data['cantidad'])
            except (ValueError, TypeError):
                return jsonify({"error": "La cantidad debe ser un número válido"}), 400
            if nueva_cantidad <= 0:
                return jsonify({"error": "La cantidad debe ser mayor a 0"}), 400
            detalle.cantidad = nueva_cantidad
        
        # Actualizar precio
        if 'precio_unidad' in data:
            try:
                nuevo_precio = float(data['precio_unidad'])
            except (ValueError, TypeError):
                return jsonify({"error": "El precio debe ser un número válido"}), 400
            if nuevo_precio <= 0:
                return jsonify({"error": "El precio unitario debe ser mayor a 0"}), 400
            detalle.precio_unidad = nuevo_precio
        
        # Recalcular subtotal
        detalle.subtotal = detalle.cantidad * detalle.precio_unidad
        
        # Actualizar total de la compra y stock del producto
        producto_afectado = Producto.query.get(detalle.producto_id)
        if producto_afectado:
            # Revertir stock antiguo, aplicar nuevo
            producto_afectado.stock -= old_cantidad
            producto_afectado.stock += detalle.cantidad
        
        # Actualizar total de la compra
        compra.total = compra.total - old_subtotal + detalle.subtotal
        
        db.session.commit()
        return jsonify({"message": "Detalle de compra actualizado", "detalle": detalle.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar detalle de compra: {str(e)}"}), 500


@main_bp.route('/detalle-compra/<int:id>', methods=['DELETE'])
@permiso_requerido("compras")
def delete_detalle_compra(id):
    try:
        detalle = DetalleCompra.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de compra no encontrado"}), 404
        
        compra = Compra.query.get(detalle.compra_id)
        producto = Producto.query.get(detalle.producto_id)
        
        # Validar que haya suficiente stock para revertir
        if producto and producto.stock < detalle.cantidad:
            return jsonify({
                "error": f"No se puede eliminar el detalle: El producto '{producto.nombre}' ya se vendió y no hay suficiente stock para revertir."
            }), 400
        
        # Revertir stock
        if producto:
            producto.stock -= detalle.cantidad
        
        # Actualizar total de la compra
        if compra:
            compra.total -= detalle.subtotal
        
        db.session.delete(detalle)
        db.session.commit()
        return jsonify({"message": "Detalle de compra eliminado correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar detalle de compra: {str(e)}"}), 500