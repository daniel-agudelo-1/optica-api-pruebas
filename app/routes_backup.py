from flask import Blueprint, jsonify, request
from app.database import db
from app.Models.models import (
    # Tablas existentes
    Marca, CategoriaProducto, Producto, Imagen,
    Multimedia,
    # Nuevas tablas principales
    Usuario, Rol, Cliente, Empleado, Proveedor, 
    Venta, Cita, Servicio, EstadoCita, EstadoVenta,
    DetalleVenta, Compra, DetalleCompra, HistorialFormula, Horario, Abono, Permiso,
    PermisoPorRol,
    # NUEVAS TABLAS PARA PEDIDOS
    Pedido, DetallePedido, CampanaSalud
)
from datetime import datetime, timedelta
from app.auth.decorators import jwt_requerido, rol_requerido
import re
EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

main_bp = Blueprint('main', __name__)

# ===== RUTA PRINCIPAL ACTUALIZADA =====
@main_bp.route('/')
def home():
    return jsonify({
        "message": "API Óptica - Sistema Completo", 
        "version": "3.0",
        "modulos_principales": {
            "clientes": "GET/POST /clientes",
            "empleados": "GET/POST /empleados", 
            "proveedores": "GET/POST /proveedores",
            "ventas": "GET/POST /ventas",
            "citas": "GET/POST /citas",
            "servicios": "GET/POST /servicios",
            "usuarios": "GET/POST /usuarios",
            "roles": "GET/POST /roles",
            "productos": "GET/POST /productos, /marcas, /categorias",
            "pedidos": "GET/POST /pedidos, /pedidos/cliente/{id}"  # ← NUEVO
        },
        "modulos_secundarios": {
            "compras": "GET/POST /compras",
            "detalle_venta": "GET/POST /detalle-venta",
            "detalle_compra": "GET/POST /detalle-compra",
            "estado_cita": "GET/POST /estado-cita",
            "estado_venta": "GET/POST /estado-venta",
            "horario": "GET/POST /horario",
            "historial_formula": "GET/POST /historial-formula",
            "abono": "GET/POST /abono",
            "permiso": "GET/POST /permiso",
            "permiso_rol": "GET/POST /permiso-rol"
        },
        "relaciones": {
            "detalles_venta": "GET /ventas/{id}/detalles",
            "detalles_compra": "GET /compras/{id}/detalles", 
            "historial_cliente": "GET /clientes/{id}/historial",
            "horarios_empleado": "GET /empleados/{id}/horarios"
        },
        "utilidades": {
            "dashboard": "GET /dashboard/estadisticas",
            "elemento_especifico": "GET /{tabla}/{id}",
            "todos_endpoints": "GET /endpoints"
        },
        "documentacion_completa": "GET /endpoints para ver todos los endpoints disponibles"
    })

# ===== MÓDULO PEDIDOS - CRUD ACTUALIZADO =====

@main_bp.route('/pedidos', methods=['GET'])
def get_pedidos():
    """Obtiene todos los pedidos"""
    try:
        pedidos = Pedido.query.all()
        return jsonify([pedido.to_dict() for pedido in pedidos])
    except Exception as e:
        return jsonify({"error": "Error al obtener pedidos"}), 500


@main_bp.route('/pedidos', methods=['POST'])
def create_pedido():
    """Crea un nuevo pedido (sin usuario)"""
    try:
        data = request.get_json()

        # Validar campos obligatorios (sin usuario_id)
        required_fields = ['cliente_id', 'metodo_pago', 'metodo_entrega']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo '{field}' es requerido"}), 400

        # Crear el pedido (el total se calculará con los items)
        pedido = Pedido(
            cliente_id=data['cliente_id'],
            metodo_pago=data['metodo_pago'],
            metodo_entrega=data['metodo_entrega'],
            direccion_entrega=data.get('direccion_entrega'),
            estado=data.get('estado', 'pendiente'),
            transferencia_comprobante=data.get('transferencia_comprobante')
        )

        # Procesar items si vienen en la petición
        total_calculado = 0
        if 'items' in data and isinstance(data['items'], list):
            for item_data in data['items']:
                # Validar campos del item
                if not all(k in item_data for k in ('producto_id', 'cantidad', 'precio_unitario')):
                    return jsonify({"error": "Cada item debe tener producto_id, cantidad y precio_unitario"}), 400

                cantidad = int(item_data['cantidad'])
                precio = float(item_data['precio_unitario'])
                subtotal = cantidad * precio

                detalle = DetallePedido(
                    producto_id=item_data['producto_id'],
                    cantidad=cantidad,
                    precio_unitario=precio,
                    subtotal=subtotal
                )
                pedido.items.append(detalle)  # Se agrega a la colección, aún sin commit
                total_calculado += subtotal

            pedido.total = total_calculado
        else:
            # Si no hay items, se requiere el campo total
            if 'total' not in data:
                return jsonify({"error": "Debe enviar 'total' o la lista de 'items'"}), 400
            pedido.total = float(data['total'])

        db.session.add(pedido)
        db.session.commit()

        return jsonify({
            "message": "Pedido creado exitosamente",
            "pedido": pedido.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear pedido: {str(e)}"}), 500


@main_bp.route('/pedidos/<int:id>', methods=['GET'])
def get_pedido(id):
    """Obtiene un pedido por su ID"""
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
        return jsonify(pedido.to_dict())
    except Exception as e:
        return jsonify({"error": "Error al obtener pedido"}), 500


@main_bp.route('/pedidos/<int:id>', methods=['PUT'])
def update_pedido(id):
    """Actualiza campos de un pedido. Si el estado cambia a 'entregado', genera la venta."""
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404

        data = request.get_json()
        estado_anterior = pedido.estado
        nuevo_estado = data.get('estado', pedido.estado)

        # Verificar si se está marcando como entregado
        if nuevo_estado == 'entregado' and estado_anterior != 'entregado':
            # Validar que el pedido pueda ser entregado (estado actual permitido)
            estados_permitidos = ['enviado', 'confirmado', 'en_preparacion']  # Ajusta según tu flujo
            if pedido.estado not in estados_permitidos:
                return jsonify({"error": f"No se puede entregar un pedido en estado '{pedido.estado}'"}), 400

            # Verificar que no tenga ya una venta asociada
            if hasattr(pedido, 'venta') and pedido.venta:
                return jsonify({"error": "Este pedido ya generó una venta anteriormente"}), 400

            # Crear la venta copiando datos del pedido
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
                estado='completada'  # Puedes cambiarlo según tu lógica (ej: 'pendiente_pago')
            )
            db.session.add(venta)
            db.session.flush()  # Para obtener el ID de la venta

            # Copiar detalles del pedido a DetalleVenta
            for detalle_pedido in pedido.items:
                detalle_venta = DetalleVenta(
                    venta_id=venta.id,
                    producto_id=detalle_pedido.producto_id,
                    cantidad=detalle_pedido.cantidad,
                    precio_unitario=detalle_pedido.precio_unitario,
                    subtotal=detalle_pedido.subtotal
                )
                db.session.add(detalle_venta)

            # Opcional: Descontar stock
            for detalle in pedido.items:
                producto = Producto.query.get(detalle.producto_id)
                if producto:
                    producto.stock -= detalle.cantidad
                    if producto.stock < 0:
                        producto.stock = 0

        # Actualizar campos normales (incluyendo estado si ya se cambió)
        if 'estado' in data:
            pedido.estado = data['estado']
        if 'transferencia_comprobante' in data:
            pedido.transferencia_comprobante = data['transferencia_comprobante']
        if 'direccion_entrega' in data:
            pedido.direccion_entrega = data['direccion_entrega']
        if 'metodo_pago' in data:
            pedido.metodo_pago = data['metodo_pago']
        if 'metodo_entrega' in data:
            pedido.metodo_entrega = data['metodo_entrega']
        if 'total' in data:
            pedido.total = float(data['total'])

        db.session.commit()
        return jsonify({
            "message": "Pedido actualizado",
            "pedido": pedido.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar pedido: {str(e)}"}), 500

@main_bp.route('/pedidos/<int:id>', methods=['DELETE'])
def delete_pedido(id):
    """Elimina un pedido siempre que no tenga una venta asociada"""
    try:
        pedido = Pedido.query.get(id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404

        # Verificar si el pedido ya generó una venta (existe registro en Venta con este pedido_id)        
        venta_asociada = Venta.query.filter_by(pedido_id=id).first()
        if venta_asociada:
            return jsonify({"error": "No se puede eliminar un pedido que ya generó una venta"}), 400

        # Eliminar detalles (aunque cascade debería hacerlo)
        DetallePedido.query.filter_by(pedido_id=id).delete()
        db.session.delete(pedido)
        db.session.commit()
        return jsonify({"message": "Pedido eliminado correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar pedido: {str(e)}"}), 500


@main_bp.route('/pedidos/cliente/<int:cliente_id>', methods=['GET'])
def get_pedidos_cliente(cliente_id):
    """Obtiene todos los pedidos de un cliente específico"""
    try:
        pedidos = Pedido.query.filter_by(cliente_id=cliente_id).order_by(Pedido.fecha.desc()).all()
        return jsonify([pedido.to_dict() for pedido in pedidos])
    except Exception as e:
        return jsonify({"error": "Error al obtener pedidos del cliente"}), 500


# ==============================
# 📸 CRUD IMÁGENES
# ==============================

# 🔹 Crear imagen
@main_bp.route('/imagenes', methods=['POST'])
def crear_imagen():
    try:
        data = request.get_json()

        if not data or not data.get('url') or not data.get('producto_id'):
            return jsonify({"error": "url y producto_id requeridos"}), 400

        producto = Producto.query.get(data['producto_id'])
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404

        imagen = Imagen(
            url=data['url'],
            producto_id=data['producto_id']
        )

        db.session.add(imagen)
        db.session.commit()

        return jsonify({
            "message": "Imagen creada",
            "imagen": imagen.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# 🔹 Obtener todas las imágenes
@main_bp.route('/imagenes', methods=['GET'])
def get_imagenes():
    try:
        imagenes = Imagen.query.all()
        return jsonify([img.to_dict() for img in imagenes])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🔹 Obtener una imagen por ID
@main_bp.route('/imagenes/<int:id>', methods=['GET'])
def get_imagen(id):
    try:
        imagen = Imagen.query.get(id)

        if not imagen:
            return jsonify({"error": "Imagen no encontrada"}), 404

        return jsonify(imagen.to_dict())

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🔹 Obtener imágenes por producto
@main_bp.route('/imagenes/producto/<int:producto_id>', methods=['GET'])
def get_imagenes_por_producto(producto_id):
    try:
        producto = Producto.query.get(producto_id)

        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404

        return jsonify({
            "producto_id": producto_id,
            "imagenes": [img.to_dict() for img in producto.imagenes]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🔹 Actualizar imagen
@main_bp.route('/imagenes/<int:id>', methods=['PUT'])
def update_imagen(id):
    try:
        imagen = Imagen.query.get(id)

        if not imagen:
            return jsonify({"error": "Imagen no encontrada"}), 404

        data = request.get_json()

        if 'url' in data:
            imagen.url = data['url']

        if 'producto_id' in data:
            producto = Producto.query.get(data['producto_id'])
            if not producto:
                return jsonify({"error": "Producto no encontrado"}), 404
            imagen.producto_id = data['producto_id']

        db.session.commit()

        return jsonify({
            "message": "Imagen actualizada",
            "imagen": imagen.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# 🔹 Eliminar imagen
@main_bp.route('/imagenes/<int:id>', methods=['DELETE'])
def delete_imagen(id):
    try:
        imagen = Imagen.query.get(id)

        if not imagen:
            return jsonify({"error": "Imagen no encontrada"}), 404

        db.session.delete(imagen)
        db.session.commit()

        return jsonify({"message": "Imagen eliminada correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ===== MÓDULO MARCAS - COMPLETAR CRUD =====# ===== MÓDULO MARCAS CON ESTADO =====
@main_bp.route('/marcas', methods=['GET'])
def get_marcas():
    try:
        marcas = Marca.query.all()
        return jsonify([marca.to_dict() for marca in marcas])
    except Exception as e:
        return jsonify({"error": "Error al obtener marcas"}), 500

@main_bp.route('/marcas', methods=['POST'])
def create_marca():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400
        
        # Crear marca con estado (por defecto true si no se envía)
        marca = Marca(
            nombre=data['nombre'],
            estado=data.get('estado', True)  # Recibir estado o usar True por defecto
        )
        db.session.add(marca)
        db.session.commit()
        return jsonify({"message": "Marca creada", "marca": marca.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear marca"}), 500

@main_bp.route('/marcas/<int:id>', methods=['PUT'])
def update_marca(id):
    try:
        marca = Marca.query.get(id)
        if not marca:
            return jsonify({"error": "Marca no encontrada"}), 404

        data = request.get_json()
        if 'nombre' in data:
            marca.nombre = data['nombre']
        if 'estado' in data:  # Permitir actualizar estado
            marca.estado = data['estado']

        db.session.commit()
        return jsonify({"message": "Marca actualizada", "marca": marca.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar marca"}), 500

@main_bp.route('/marcas/<int:id>', methods=['DELETE'])
def delete_marca(id):
    try:
        marca = Marca.query.get(id)
        if not marca:
            return jsonify({"error": "Marca no encontrada"}), 404

        db.session.delete(marca)
        db.session.commit()
        return jsonify({"message": "Marca eliminada correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar marca"}), 500

# ===== MÓDULO CATEGORÍAS - COMPLETAR CRUD =====
@main_bp.route('/categorias', methods=['GET'])
def get_categorias():
    try:
        categorias = CategoriaProducto.query.all()
        return jsonify([categoria.to_dict() for categoria in categorias])
    except Exception as e:
        return jsonify({"error": "Error al obtener categorías"}), 500

@main_bp.route('/categorias', methods=['POST'])
def create_categoria():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400
        
        # Crear categoría con estado (por defecto true si no se envía)
        categoria = CategoriaProducto(
            nombre=data['nombre'],
            descripcion=data.get('descripcion', ''),  # Campo adicional que tiene categorías
            estado=data.get('estado', True)  # Recibir estado o usar True por defecto
        )
        db.session.add(categoria)
        db.session.commit()
        return jsonify({"message": "Categoría creada", "categoria": categoria.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear categoría"}), 500

@main_bp.route('/categorias/<int:id>', methods=['PUT'])
def update_categoria(id):
    try:
        categoria = CategoriaProducto.query.get(id)
        if not categoria:
            return jsonify({"error": "Categoría no encontrada"}), 404

        data = request.get_json()
        if 'nombre' in data:
            categoria.nombre = data['nombre']
        if 'descripcion' in data:  # Campo adicional de categorías
            categoria.descripcion = data['descripcion']
        if 'estado' in data:  # Permitir actualizar estado
            categoria.estado = data['estado']

        db.session.commit()
        return jsonify({"message": "Categoría actualizada", "categoria": categoria.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar categoría"}), 500

@main_bp.route('/categorias/<int:id>', methods=['DELETE'])
def delete_categoria(id):
    try:
        categoria = CategoriaProducto.query.get(id)
        if not categoria:
            return jsonify({"error": "Categoría no encontrada"}), 404

        db.session.delete(categoria)
        db.session.commit()
        return jsonify({"message": "Categoría eliminada correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar categoría"}), 500

# ===== MÓDULO PRODUCTOS - COMPLETAR CRUD (IGUAL A EMPLEADOS) =====
@main_bp.route('/productos', methods=['GET'])
def get_productos():
    try:
        productos = Producto.query.all()
        return jsonify([producto.to_dict() for producto in productos])
    except Exception as e:
        return jsonify({"error": "Error al obtener productos"}), 500

@main_bp.route('/productos', methods=['POST'])
def create_producto():
    try:
        data = request.get_json()
        required_fields = ['nombre', 'precio_venta', 'precio_compra', 'categoria_id', 'marca_id']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        producto = Producto(
            nombre=data['nombre'],
            precio_venta=float(data['precio_venta']),
            precio_compra=float(data['precio_compra']),
            stock=data.get('stock', 0),
            stock_minimo=data.get('stock_minimo', 5),
            descripcion=data.get('descripcion', ''),
            categoria_producto_id=data['categoria_id'],
            marca_id=data['marca_id'],
            estado=data.get('estado', True)  # 👈 IGUAL QUE EMPLEADOS
        )
        db.session.add(producto)
        db.session.commit()
        return jsonify({"message": "Producto creado", "producto": producto.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear producto"}), 500

@main_bp.route('/productos/<int:id>', methods=['PUT'])
def update_producto(id):
    try:
        producto = Producto.query.get(id)
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404

        data = request.get_json()
        
        # Actualizar campos si vienen en la petición (IGUAL QUE EMPLEADOS)
        if 'nombre' in data:
            producto.nombre = data['nombre']
        if 'precio_venta' in data:
            producto.precio_venta = float(data['precio_venta'])
        if 'precio_compra' in data:
            producto.precio_compra = float(data['precio_compra'])
        if 'stock' in data:
            producto.stock = data['stock']
        if 'stock_minimo' in data:
            producto.stock_minimo = data['stock_minimo']
        if 'descripcion' in data:
            producto.descripcion = data['descripcion']
        if 'categoria_id' in data:
            producto.categoria_producto_id = data['categoria_id']
        if 'marca_id' in data:
            producto.marca_id = data['marca_id']
        if 'estado' in data:  # 👈 IGUAL QUE EMPLEADOS para cambio de estado
            producto.estado = data['estado']

        db.session.commit()
        return jsonify({"message": "Producto actualizado", "producto": producto.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar producto"}), 500

@main_bp.route('/productos/<int:id>', methods=['DELETE'])
def delete_producto(id):
    try:
        producto = Producto.query.get(id)
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404

        db.session.delete(producto)
        db.session.commit()
        return jsonify({"message": "Producto eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar producto"}), 500
    
# ===== MÓDULO CLIENTES - COMPLETAR CRUD =====
@main_bp.route('/clientes', methods=['GET'])
def get_clientes():
    try:
        clientes = Cliente.query.all()
        return jsonify([cliente.to_dict() for cliente in clientes])
    except Exception as e:
        return jsonify({"error": "Error al obtener clientes"}), 500

@main_bp.route('/clientes', methods=['POST'])
def create_cliente():
    try:
        data = request.get_json()
        required_fields = ['nombre', 'apellido', 'numero_documento', 'fecha_nacimiento']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Verificar si ya existe cliente con este documento
        cliente_existente = Cliente.query.filter_by(numero_documento=data['numero_documento']).first()
        if cliente_existente:
            return jsonify({
                "success": False,
                "error": "Ya existe un cliente con este número de documento"
            }), 400

        cliente = Cliente(
            nombre=data['nombre'],
            apellido=data['apellido'],
            tipo_documento=data.get('tipo_documento'),
            numero_documento=data['numero_documento'],
            fecha_nacimiento=datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date(),
            genero=data.get('genero'),
            telefono=data.get('telefono'),
            correo=data.get('correo'),
            municipio=data.get('municipio'),
            direccion=data.get('direccion'),
            ocupacion=data.get('ocupacion'),
            telefono_emergencia=data.get('telefono_emergencia'),
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
        return jsonify({
            "success": False,
            "error": f"Error al crear cliente: {str(e)}"
        }), 500

@main_bp.route('/clientes/<int:id>', methods=['PUT'])
def update_cliente(id):
    try:
        cliente = Cliente.query.get(id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        data = request.get_json()
        
        # Campos actualizables
        if 'nombre' in data:
            cliente.nombre = data['nombre']
        if 'apellido' in data:
            cliente.apellido = data['apellido']
        if 'tipo_documento' in data:
            cliente.tipo_documento = data['tipo_documento']
        if 'numero_documento' in data:
            cliente.numero_documento = data['numero_documento']
        if 'fecha_nacimiento' in data:
            cliente.fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        if 'genero' in data:
            cliente.genero = data['genero']
        if 'telefono' in data:
            cliente.telefono = data['telefono']
        if 'correo' in data:
            cliente.correo = data['correo']
        if 'municipio' in data:
            cliente.municipio = data['municipio']
        if 'direccion' in data:
            cliente.direccion = data['direccion']
        if 'ocupacion' in data:
            cliente.ocupacion = data['ocupacion']
        if 'telefono_emergencia' in data:
            cliente.telefono_emergencia = data['telefono_emergencia']

        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Cliente actualizado exitosamente",
            "cliente": cliente.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": f"Error al actualizar cliente: {str(e)}"
        }), 500

@main_bp.route('/clientes/<int:id>', methods=['DELETE'])
def delete_cliente(id):
    try:
        cliente = Cliente.query.get(id)
        if not cliente:
            return jsonify({"error": "Cliente no encontrado"}), 404

        db.session.delete(cliente)
        db.session.commit()
        return jsonify({"message": "Cliente eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar cliente"}), 500

# ===== MÓDULO EMPLEADOS - COMPLETAR CRUD =====
@main_bp.route('/empleados', methods=['GET'])
def get_empleados():
    try:
        empleados = Empleado.query.all()
        return jsonify([empleado.to_dict() for empleado in empleados])
    except Exception as e:
        return jsonify({"error": "Error al obtener empleados"}), 500

@main_bp.route('/empleados', methods=['POST'])
def create_empleado():
    try:
        data = request.get_json()
        required_fields = ['nombre', 'numero_documento', 'fecha_ingreso']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        empleado = Empleado(
            nombre=data['nombre'],
            tipo_documento=data.get('tipo_documento'),
            numero_documento=data['numero_documento'],
            telefono=data.get('telefono'),
            correo=data.get('correo'),  # 👈 AGREGAR ESTA LÍNEA
            direccion=data.get('direccion'),
            fecha_ingreso=datetime.strptime(data['fecha_ingreso'], '%Y-%m-%d').date(),
            cargo=data.get('cargo'),
            estado=data.get('estado', True)  # 👈 AGREGAR ESTADO
        )
        db.session.add(empleado)
        db.session.commit()
        return jsonify({"message": "Empleado creado", "empleado": empleado.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear empleado"}), 500

@main_bp.route('/empleados/<int:id>', methods=['PUT'])
def update_empleado(id):
    try:
        empleado = Empleado.query.get(id)
        if not empleado:
            return jsonify({"error": "Empleado no encontrado"}), 404

        data = request.get_json()
        
        # Actualizar campos si vienen en la petición
        if 'nombre' in data:
            empleado.nombre = data['nombre']
        if 'tipo_documento' in data:
            empleado.tipo_documento = data['tipo_documento']
        if 'numero_documento' in data:
            empleado.numero_documento = data['numero_documento']
        if 'telefono' in data:
            empleado.telefono = data['telefono']
        if 'correo' in data:  # 👈 AGREGAR ESTA LÍNEA
            empleado.correo = data['correo']
        if 'direccion' in data:
            empleado.direccion = data['direccion']
        if 'fecha_ingreso' in data:
            empleado.fecha_ingreso = datetime.strptime(data['fecha_ingreso'], '%Y-%m-%d').date()
        if 'cargo' in data:
            empleado.cargo = data['cargo']
        if 'estado' in data:  # 👈 AGREGAR ESTA LÍNEA para cambio de estado
            empleado.estado = data['estado']

        db.session.commit()
        return jsonify({"message": "Empleado actualizado", "empleado": empleado.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar empleado"}), 500

@main_bp.route('/empleados/<int:id>', methods=['DELETE'])
def delete_empleado(id):
    try:
        empleado = Empleado.query.get(id)
        if not empleado:
            return jsonify({"error": "Empleado no encontrado"}), 404

        db.session.delete(empleado)
        db.session.commit()
        return jsonify({"message": "Empleado eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar empleado"}), 500
    

# ===== MÓDULO PROVEEDORES - COMPLETAR CRUD CON ESTADO =====
@main_bp.route('/proveedores', methods=['GET'])
def get_proveedores():
    try:
        proveedores = Proveedor.query.all()
        return jsonify([proveedor.to_dict() for proveedor in proveedores])
    except Exception as e:
        return jsonify({"error": "Error al obtener proveedores"}), 500

@main_bp.route('/proveedores', methods=['POST'])
def create_proveedor():
    try:
        data = request.get_json()
        if not data.get('razon_social_o_nombre'):
            return jsonify({"error": "La razón social o nombre es requerido"}), 400

        proveedor = Proveedor(
            tipo_proveedor=data.get('tipo_proveedor'),
            tipo_documento=data.get('tipo_documento'),
            documento=data.get('documento'),
            razon_social_o_nombre=data['razon_social_o_nombre'],
            contacto=data.get('contacto'),
            telefono=data.get('telefono'),
            correo=data.get('correo'),
            departamento=data.get('departamento'),
            municipio=data.get('municipio'),
            direccion=data.get('direccion'),
            estado=data.get('estado', True)  # 👈 AGREGAR ESTADO (por defecto True)
        )
        db.session.add(proveedor)
        db.session.commit()
        return jsonify({"message": "Proveedor creado", "proveedor": proveedor.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear proveedor"}), 500

@main_bp.route('/proveedores/<int:id>', methods=['PUT'])
def update_proveedor(id):
    try:
        proveedor = Proveedor.query.get(id)
        if not proveedor:
            return jsonify({"error": "Proveedor no encontrado"}), 404

        data = request.get_json()
        
        # Actualizar campos si vienen en la petición
        if 'tipo_proveedor' in data:
            proveedor.tipo_proveedor = data['tipo_proveedor']
        if 'tipo_documento' in data:
            proveedor.tipo_documento = data['tipo_documento']
        if 'documento' in data:
            proveedor.documento = data['documento']
        if 'razon_social_o_nombre' in data:
            proveedor.razon_social_o_nombre = data['razon_social_o_nombre']
        if 'contacto' in data:
            proveedor.contacto = data['contacto']
        if 'telefono' in data:
            proveedor.telefono = data['telefono']
        if 'correo' in data:
            proveedor.correo = data['correo']
        if 'departamento' in data:
            proveedor.departamento = data['departamento']
        if 'municipio' in data:
            proveedor.municipio = data['municipio']
        if 'direccion' in data:
            proveedor.direccion = data['direccion']
        if 'estado' in data:  # 👈 AGREGAR ESTA LÍNEA para cambio de estado
            proveedor.estado = data['estado']

        db.session.commit()
        return jsonify({"message": "Proveedor actualizado", "proveedor": proveedor.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar proveedor"}), 500

@main_bp.route('/proveedores/<int:id>', methods=['DELETE'])
def delete_proveedor(id):
    try:
        proveedor = Proveedor.query.get(id)
        if not proveedor:
            return jsonify({"error": "Proveedor no encontrado"}), 404

        db.session.delete(proveedor)
        db.session.commit()
        return jsonify({"message": "Proveedor eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar proveedor"}), 500

# ===== MÓDULO USUARIOS - COMPLETAR CRUD =====

@main_bp.route('/usuarios', methods=['GET'])
@jwt_requerido
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
                usuarios_list.append({
                    'id': usuario.id,
                    'nombre': usuario.nombre,
                    'correo': usuario.correo,
                    'rol_id': usuario.rol_id,
                    'estado': usuario.estado
                })
        
        return jsonify(usuarios_list)
    except Exception as e:
        print(f"❌ ERROR CRÍTICO en get_usuarios: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error al obtener usuarios: {str(e)}"}), 500


@main_bp.route('/usuarios/<int:id>/completo', methods=['GET'])
@jwt_requerido
def get_usuario_completo(id):
    try:
        usuario = Usuario.query.get(id)
        if not usuario:
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404
        
        respuesta = {
            "usuario": usuario.to_dict(),
            "cliente": None
        }
        
        if usuario.cliente_id:
            cliente = Cliente.query.get(usuario.cliente_id)
            if cliente:
                respuesta["cliente"] = cliente.to_dict()
        
        return jsonify({"success": True, "data": respuesta})
        
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al obtener usuario completo: {str(e)}"}), 500


@main_bp.route('/usuarios/email/<string:email>', methods=['GET'])
@jwt_requerido
def get_usuario_por_email(email):
    try:
        usuario = Usuario.query.filter_by(correo=email).first()
        if not usuario:
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404
        
        return jsonify({
            "success": True,
            "usuario": {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "correo": usuario.correo,
                "rol_id": usuario.rol_id,
                "cliente_id": usuario.cliente_id
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al buscar usuario: {str(e)}"}), 500


@main_bp.route('/usuarios', methods=['POST'])
@rol_requerido('admin', 'superadmin')
def create_usuario():
    try:
        data = request.get_json()
        required_fields = ['nombre', 'correo', 'contrasenia', 'rol_id']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Validar correo
        if not EMAIL_REGEX.match(data['correo'].strip().lower()):
            return jsonify({"error": "Formato de correo inválido"}), 400

        # Validar contraseña
        if len(data['contrasenia']) < 6:
            return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400

        # Verificar correo duplicado
        if Usuario.query.filter_by(correo=data['correo'].strip().lower()).first():
            return jsonify({"success": False, "error": "El correo ya está registrado"}), 400

        # Verificar que el rol existe y está activo
        rol = Rol.query.get(data['rol_id'])
        if not rol:
            return jsonify({"error": "El rol especificado no existe"}), 400
        if not rol.estado:
            return jsonify({"error": "No puedes asignar un rol inactivo"}), 400

        # Encriptar contraseña
        from werkzeug.security import generate_password_hash
        contrasenia_hash = generate_password_hash(data['contrasenia'])

        cliente_id = None

        if data['rol_id'] == 2:
            nombre_parts = data['nombre'].split(' ')
            primer_nombre = nombre_parts[0]
            apellido = nombre_parts[1] if len(nombre_parts) > 1 else ''

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
            contrasenia=contrasenia_hash,  # ✅ siempre encriptada
            rol_id=data['rol_id'],
            estado=data.get('estado', True),
            cliente_id=cliente_id
        )
        db.session.add(usuario)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Usuario creado exitosamente",
            "usuario": usuario.to_dict(),
            "cliente_id": cliente_id
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": f"Error al crear usuario: {str(e)}"}), 500


@main_bp.route('/clientes/usuario/<int:usuario_id>', methods=['GET'])
@jwt_requerido
def get_cliente_by_usuario(usuario_id):
    try:
        usuario = Usuario.query.get(usuario_id)
        if not usuario:
            return jsonify({"success": False, "error": "Usuario no encontrado"}), 404
        
        if not usuario.cliente_id:
            return jsonify({"success": False, "error": "Este usuario no tiene cliente asociado"}), 404
        
        cliente = Cliente.query.get(usuario.cliente_id)
        if not cliente:
            return jsonify({"success": False, "error": "Cliente no encontrado"}), 404
        
        return jsonify({"success": True, "cliente": cliente.to_dict()})
        
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al obtener cliente: {str(e)}"}), 500


@main_bp.route('/usuarios/<int:id>', methods=['PUT'])
@rol_requerido('admin', 'superadmin')
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
            from werkzeug.security import generate_password_hash
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
@rol_requerido('admin', 'superadmin')
def delete_usuario(id):
    try:
        usuario = Usuario.query.get(id)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # No eliminar si está activo
        if usuario.estado:
            return jsonify({
                "error": "Debes desactivar el usuario antes de eliminarlo"
            }), 400

        db.session.delete(usuario)
        db.session.commit()
        return jsonify({"message": "Usuario eliminado correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar usuario"}), 500
# ===== MÓDULO ROLES - COMPLETAR CRUD =====
# Roles críticos que no se pueden tocar
ROLES_CRITICOS = ['admin', 'superadmin']

@main_bp.route('/roles', methods=['GET'])
@jwt_requerido
def get_roles():
    try:
        roles = Rol.query.all()
        return jsonify([rol.to_dict() for rol in roles])
    except Exception as e:
        return jsonify({"error": "Error al obtener roles"}), 500


@main_bp.route('/roles', methods=['POST'])
@rol_requerido('admin', 'superadmin')
def create_rol():
    try:
        data = request.get_json()

        if not data or not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400

        # Validar longitud del nombre
        nombre = data['nombre'].strip()
        if len(nombre) < 3 or len(nombre) > 25:
            return jsonify({"error": "El nombre debe tener entre 3 y 25 caracteres"}), 400

        # No permitir crear roles críticos
        if nombre.lower() in ROLES_CRITICOS:
            return jsonify({"error": "No puedes crear un rol con ese nombre"}), 403

        # Validar duplicado
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

        rol = Rol(
            nombre=nombre,
            descripcion=data.get('descripcion', '').strip(),
            estado=estado_bool
        )
        rol.permisos = permisos

        db.session.add(rol)
        db.session.commit()

        return jsonify({"message": "Rol creado", "rol": rol.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear rol"}), 500


@main_bp.route('/roles/<int:id>', methods=['PUT'])
@rol_requerido('admin', 'superadmin')
def update_rol(id):
    try:
        rol = Rol.query.get(id)
        if not rol:
            return jsonify({"error": "Rol no encontrado"}), 404

        # No permitir editar roles críticos
        if rol.nombre.lower() in ROLES_CRITICOS:
            return jsonify({"error": "No puedes modificar este rol"}), 403

        data = request.get_json()

        if 'nombre' in data:
            nombre = data['nombre'].strip()
            if len(nombre) < 3 or len(nombre) > 25:
                return jsonify({"error": "El nombre debe tener entre 3 y 25 caracteres"}), 400

            # Verificar duplicado (excluyendo el mismo rol)
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

            # No desactivar si tiene usuarios activos
            if not nuevo_estado:
                usuarios_activos = Usuario.query.filter_by(
                    rol_id=id, estado=True
                ).count()
                if usuarios_activos > 0:
                    return jsonify({
                        "error": f"No puedes desactivar este rol: tiene {usuarios_activos} usuario(s) activo(s)"
                    }), 400

            rol.estado = nuevo_estado

        if 'permisos' in data:
            permisos_ids = data['permisos']
            # Eliminar duplicados
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
@rol_requerido('admin', 'superadmin')
def delete_rol(id):
    try:
        rol = Rol.query.get(id)
        if not rol:
            return jsonify({"error": "Rol no encontrado"}), 404

        # No eliminar roles críticos
        if rol.nombre.lower() in ROLES_CRITICOS:
            return jsonify({"error": "No puedes eliminar este rol"}), 403

        # No eliminar si está activo
        if rol.estado:
            return jsonify({
                "error": "Debes desactivar el rol antes de eliminarlo"
            }), 400

        # No eliminar si tiene usuarios (activos o inactivos)
        usuarios_count = Usuario.query.filter_by(rol_id=id).count()
        if usuarios_count > 0:
            return jsonify({
                "error": f"No puedes eliminar este rol: tiene {usuarios_count} usuario(s) asignado(s)"
            }), 400

        db.session.delete(rol)
        db.session.commit()
        return jsonify({"message": "Rol eliminado correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar rol"}), 500


# ===== MÓDULO VENTAS - CRUD (SIN CREACIÓN MANUAL) =====

@main_bp.route('/ventas', methods=['GET'])
def get_ventas():
    """Obtiene todas las ventas"""
    try:
        ventas = Venta.query.all()
        return jsonify([venta.to_dict() for venta in ventas])
    except Exception as e:
        return jsonify({"error": "Error al obtener ventas"}), 500


@main_bp.route('/ventas/<int:id>', methods=['GET'])
def get_venta(id):
    """Obtiene una venta por su ID"""
    try:
        venta = Venta.query.get(id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404
        return jsonify(venta.to_dict())
    except Exception as e:
        return jsonify({"error": "Error al obtener venta"}), 500


@main_bp.route('/ventas/<int:id>', methods=['PUT'])
def update_venta(id):
    """
    Actualiza campos de una venta.
    No se puede cambiar el pedido asociado ni el cliente.
    Solo se permiten actualizaciones en:
    - estado
    - metodo_pago
    - metodo_entrega
    - direccion_entrega
    - transferencia_comprobante
    - total (con precaución)
    """
    try:
        venta = Venta.query.get(id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404

        data = request.get_json()

        # Campos editables (no se permite modificar pedido_id ni cliente_id)
        if 'estado' in data:
            venta.estado = data['estado']
        if 'metodo_pago' in data:
            venta.metodo_pago = data['metodo_pago']
        if 'metodo_entrega' in data:
            venta.metodo_entrega = data['metodo_entrega']
        if 'direccion_entrega' in data:
            venta.direccion_entrega = data['direccion_entrega']
        if 'transferencia_comprobante' in data:
            venta.transferencia_comprobante = data['transferencia_comprobante']
        if 'total' in data:
            # Opcional: podrías validar que el nuevo total no sea menor a lo ya abonado
            venta.total = float(data['total'])

        db.session.commit()
        return jsonify({
            "message": "Venta actualizada",
            "venta": venta.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar venta: {str(e)}"}), 500


@main_bp.route('/ventas/<int:id>', methods=['DELETE'])
def delete_venta(id):
    """
    Elimina una venta solo si no tiene abonos asociados.
    Previene la pérdida de información financiera.
    """
    try:
        venta = Venta.query.get(id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404

        # Verificar si tiene abonos registrados
        if venta.abonos and len(venta.abonos) > 0:
            return jsonify({"error": "No se puede eliminar una venta con abonos registrados"}), 400

        # Opcional: verificar detalles, aunque se pueden eliminar en cascada si la BD lo permite
        db.session.delete(venta)
        db.session.commit()
        return jsonify({"message": "Venta eliminada correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar venta: {str(e)}"}), 500

# ===== MÓDULO CITAS - COMPLETAR CRUD =====
@main_bp.route('/citas', methods=['GET'])
def get_citas():
    try:
        citas = Cita.query.all()
        return jsonify([cita.to_dict() for cita in citas])
    except Exception as e:
        return jsonify({"error": "Error al obtener citas"}), 500

@main_bp.route('/citas', methods=['POST'])
def create_cita():
    try:
        data = request.get_json()
        required_fields = ['cliente_id', 'servicio_id', 'empleado_id', 
                          'estado_cita_id', 'fecha', 'hora']  # ← fecha y hora separados
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Parsear fecha (solo fecha: YYYY-MM-DD)
        fecha_date = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
        
        # Parsear hora (HH:MM o HH:MM:SS)
        hora_str = data['hora']
        if hora_str.count(':') == 1:
            # Formato HH:MM
            hora_time = datetime.strptime(hora_str, '%H:%M').time()
        else:
            # Formato HH:MM:SS
            hora_time = datetime.strptime(hora_str, '%H:%M:%S').time()

        cita = Cita(
            cliente_id=data['cliente_id'],
            servicio_id=data['servicio_id'],
            empleado_id=data['empleado_id'],
            estado_cita_id=data['estado_cita_id'],
            metodo_pago=data.get('metodo_pago'),
            hora=hora_time,  # ← Hora separada
            duracion=data.get('duracion', 30),
            fecha=fecha_date  # ← Solo fecha
        )
        db.session.add(cita)
        db.session.commit()
        return jsonify({"message": "Cita creada", "cita": cita.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear cita: {str(e)}"}), 500

@main_bp.route('/citas/<int:id>', methods=['PUT'])
def update_cita(id):
    try:
        cita = Cita.query.get(id)
        if not cita:
            return jsonify({"error": "Cita no encontrada"}), 404

        data = request.get_json()
        if 'cliente_id' in data:
            cita.cliente_id = data['cliente_id']
        if 'servicio_id' in data:
            cita.servicio_id = data['servicio_id']
        if 'empleado_id' in data:
            cita.empleado_id = data['empleado_id']
        if 'estado_cita_id' in data:
            cita.estado_cita_id = data['estado_cita_id']
        if 'metodo_pago' in data:
            cita.metodo_pago = data['metodo_pago']
        if 'hora' in data:
            # Parsear hora
            hora_str = data['hora']
            if hora_str.count(':') == 1:
                cita.hora = datetime.strptime(hora_str, '%H:%M').time()
            else:
                cita.hora = datetime.strptime(hora_str, '%H:%M:%S').time()
        if 'duracion' in data:
            cita.duracion = data['duracion']
        if 'fecha' in data:
            cita.fecha = datetime.strptime(data['fecha'], '%Y-%m-%d').date()

        db.session.commit()
        return jsonify({"message": "Cita actualizada", "cita": cita.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar cita: {str(e)}"}), 500

@main_bp.route('/citas/<int:id>', methods=['DELETE'])
def delete_cita(id):
    try:
        cita = Cita.query.get(id)
        if not cita:
            return jsonify({"error": "Cita no encontrada"}), 404

        db.session.delete(cita)
        db.session.commit()
        return jsonify({"message": "Cita eliminada correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar cita"}), 500

# ===== MÓDULO SERVICIOS - COMPLETAR CRUD CON ESTADO =====
@main_bp.route('/servicios', methods=['GET'])
def get_servicios():
    try:
        servicios = Servicio.query.all()
        return jsonify([servicio.to_dict() for servicio in servicios])
    except Exception as e:
        return jsonify({"error": "Error al obtener servicios"}), 500

@main_bp.route('/servicios', methods=['POST'])
def create_servicio():
    try:
        data = request.get_json()
        required_fields = ['nombre', 'duracion_min', 'precio']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        servicio = Servicio(
            nombre=data['nombre'],
            duracion_min=data['duracion_min'],
            precio=float(data['precio']),
            descripcion=data.get('descripcion', ''),
            estado=data.get('estado', True)  # 👈 AGREGAR ESTADO (por defecto True)
        )
        db.session.add(servicio)
        db.session.commit()
        return jsonify({"message": "Servicio creado", "servicio": servicio.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear servicio"}), 500

@main_bp.route('/servicios/<int:id>', methods=['PUT'])
def update_servicio(id):
    try:
        servicio = Servicio.query.get(id)
        if not servicio:
            return jsonify({"error": "Servicio no encontrado"}), 404

        data = request.get_json()
        
        # Actualizar campos si vienen en la petición
        if 'nombre' in data:
            servicio.nombre = data['nombre']
        if 'duracion_min' in data:
            servicio.duracion_min = data['duracion_min']
        if 'precio' in data:
            servicio.precio = float(data['precio'])
        if 'descripcion' in data:
            servicio.descripcion = data['descripcion']
        if 'estado' in data:  # 👈 AGREGAR ESTA LÍNEA para cambio de estado
            servicio.estado = data['estado']

        db.session.commit()
        return jsonify({"message": "Servicio actualizado", "servicio": servicio.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar servicio"}), 500

@main_bp.route('/servicios/<int:id>', methods=['DELETE'])
def delete_servicio(id):
    try:
        servicio = Servicio.query.get(id)
        if not servicio:
            return jsonify({"error": "Servicio no encontrado"}), 404

        db.session.delete(servicio)
        db.session.commit()
        return jsonify({"message": "Servicio eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar servicio"}), 500

# ===== MÓDULO COMPRAS - COMPLETAR CRUD =====
@main_bp.route('/compras', methods=['GET'])
def get_compras():
    try:
        compras = Compra.query.all()
        return jsonify([compra.to_dict() for compra in compras])
    except Exception as e:
        return jsonify({"error": "Error al obtener compras"}), 500

@main_bp.route('/compras', methods=['POST'])
def create_compra():
    try:
        data = request.get_json()
        required_fields = ['proveedor_id', 'total']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        compra = Compra(
            proveedor_id=data['proveedor_id'],
            total=float(data['total']),
            estado_compra=data.get('estado_compra', True)
        )
        db.session.add(compra)
        db.session.commit()
        return jsonify({"message": "Compra creada", "compra": compra.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear compra"}), 500

@main_bp.route('/compras/<int:id>', methods=['PUT'])
def update_compra(id):
    try:
        compra = Compra.query.get(id)
        if not compra:
            return jsonify({"error": "Compra no encontrada"}), 404

        data = request.get_json()
        if 'proveedor_id' in data:
            compra.proveedor_id = data['proveedor_id']
        if 'total' in data:
            compra.total = float(data['total'])
        if 'estado_compra' in data:
            compra.estado_compra = data['estado_compra']

        db.session.commit()
        return jsonify({"message": "Compra actualizada", "compra": compra.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar compra"}), 500

@main_bp.route('/compras/<int:id>', methods=['DELETE'])
def delete_compra(id):
    try:
        compra = Compra.query.get(id)
        if not compra:
            return jsonify({"error": "Compra no encontrada"}), 404

        db.session.delete(compra)
        db.session.commit()
        return jsonify({"message": "Compra eliminada correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar compra"}), 500

# ===== TABLAS SECUNDARIAS - DETALLES VENTA - COMPLETAR CRUD =====
@main_bp.route('/detalle-venta', methods=['GET'])
def get_detalles_venta():
    try:
        detalles = DetalleVenta.query.all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": "Error al obtener detalles de venta"}), 500

@main_bp.route('/detalle-venta', methods=['POST'])
def create_detalle_venta():
    try:
        data = request.get_json()
        required_fields = ['venta_id', 'producto_id', 'cantidad', 'precio_unitario']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        detalle = DetalleVenta(
            venta_id=data['venta_id'],
            producto_id=data['producto_id'],
            cantidad=data['cantidad'],
            precio_unitario=float(data['precio_unitario']),
            descuento=data.get('descuento', 0.0),
            subtotal=float(data['cantidad']) * float(data['precio_unitario']) - float(data.get('descuento', 0.0))
        )
        db.session.add(detalle)
        db.session.commit()
        return jsonify({"message": "Detalle de venta creado", "detalle": detalle.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear detalle de venta"}), 500

@main_bp.route('/detalle-venta/<int:id>', methods=['PUT'])
def update_detalle_venta(id):
    try:
        detalle = DetalleVenta.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de venta no encontrado"}), 404

        data = request.get_json()
        if 'venta_id' in data:
            detalle.venta_id = data['venta_id']
        if 'producto_id' in data:
            detalle.producto_id = data['producto_id']
        if 'cantidad' in data:
            detalle.cantidad = data['cantidad']
        if 'precio_unitario' in data:
            detalle.precio_unitario = float(data['precio_unitario'])
        if 'descuento' in data:
            detalle.descuento = float(data['descuento'])
        if 'cantidad' in data and 'precio_unitario' in data:
            detalle.subtotal = float(data['cantidad']) * float(data['precio_unitario']) - float(data.get('descuento', detalle.descuento))

        db.session.commit()
        return jsonify({"message": "Detalle de venta actualizado", "detalle": detalle.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar detalle de venta"}), 500

@main_bp.route('/detalle-venta/<int:id>', methods=['DELETE'])
def delete_detalle_venta(id):
    try:
        detalle = DetalleVenta.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de venta no encontrado"}), 404

        db.session.delete(detalle)
        db.session.commit()
        return jsonify({"message": "Detalle de venta eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar detalle de venta"}), 500

# ===== TABLAS SECUNDARIAS - DETALLES PEDIDO - CRUD =====

@main_bp.route('/detalle-pedido', methods=['GET'])
def get_detalles_pedido():
    """Lista todos los detalles de pedido (opcional: filtrar por pedido_id)"""
    try:
        # Si se pasa ?pedido_id=... en la query string, filtrar
        pedido_id = request.args.get('pedido_id', type=int)
        if pedido_id:
            detalles = DetallePedido.query.filter_by(pedido_id=pedido_id).all()
        else:
            detalles = DetallePedido.query.all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": "Error al obtener detalles de pedido"}), 500


@main_bp.route('/detalle-pedido', methods=['POST'])
def create_detalle_pedido():
    """Crea un nuevo detalle para un pedido existente"""
    try:
        data = request.get_json()
        required_fields = ['pedido_id', 'producto_id', 'cantidad', 'precio_unitario']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo '{field}' es requerido"}), 400

        # Verificar que el pedido exista
        pedido = Pedido.query.get(data['pedido_id'])
        if not pedido:
            return jsonify({"error": "El pedido especificado no existe"}), 404

        # Verificar que el pedido no esté ya entregado o cancelado (opcional, según reglas de negocio)
        if pedido.estado in ['entregado', 'cancelado']:
            return jsonify({"error": f"No se puede modificar un pedido en estado '{pedido.estado}'"}), 400

        # Calcular subtotal
        cantidad = int(data['cantidad'])
        precio = float(data['precio_unitario'])
        subtotal = cantidad * precio

        detalle = DetallePedido(
            pedido_id=data['pedido_id'],
            producto_id=data['producto_id'],
            cantidad=cantidad,
            precio_unitario=precio,
            subtotal=subtotal
        )
        db.session.add(detalle)

        # Actualizar el total del pedido (sumar el nuevo subtotal)
        pedido.total += subtotal

        db.session.commit()
        return jsonify({
            "message": "Detalle de pedido creado",
            "detalle": detalle.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear detalle de pedido: {str(e)}"}), 500


@main_bp.route('/detalle-pedido/<int:id>', methods=['PUT'])
def update_detalle_pedido(id):
    """Actualiza un detalle de pedido existente (cantidad, precio, etc.)"""
    try:
        detalle = DetallePedido.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de pedido no encontrado"}), 404

        pedido = Pedido.query.get(detalle.pedido_id)
        if not pedido:
            return jsonify({"error": "El pedido asociado no existe"}), 404

        # No permitir modificación si el pedido ya está entregado o cancelado
        if pedido.estado in ['entregado', 'cancelado']:
            return jsonify({"error": f"No se puede modificar un pedido en estado '{pedido.estado}'"}), 400

        data = request.get_json()
        # Guardar valores antiguos para actualizar el total del pedido
        old_subtotal = detalle.subtotal

        # Actualizar campos
        if 'producto_id' in data:
            detalle.producto_id = data['producto_id']
        if 'cantidad' in data:
            detalle.cantidad = int(data['cantidad'])
        if 'precio_unitario' in data:
            detalle.precio_unitario = float(data['precio_unitario'])

        # Recalcular subtotal
        nuevo_subtotal = detalle.cantidad * detalle.precio_unitario
        detalle.subtotal = nuevo_subtotal

        # Ajustar el total del pedido (restar antiguo, sumar nuevo)
        pedido.total = pedido.total - old_subtotal + nuevo_subtotal

        db.session.commit()
        return jsonify({
            "message": "Detalle de pedido actualizado",
            "detalle": detalle.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar detalle de pedido: {str(e)}"}), 500


@main_bp.route('/detalle-pedido/<int:id>', methods=['DELETE'])
def delete_detalle_pedido(id):
    """Elimina un detalle de pedido y actualiza el total del pedido"""
    try:
        detalle = DetallePedido.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de pedido no encontrado"}), 404

        pedido = Pedido.query.get(detalle.pedido_id)
        if not pedido:
            return jsonify({"error": "El pedido asociado no existe"}), 404

        # No permitir eliminación si el pedido ya está entregado o cancelado
        if pedido.estado in ['entregado', 'cancelado']:
            return jsonify({"error": f"No se puede modificar un pedido en estado '{pedido.estado}'"}), 400

        # Restar el subtotal del total del pedido
        pedido.total -= detalle.subtotal

        db.session.delete(detalle)
        db.session.commit()
        return jsonify({"message": "Detalle de pedido eliminado correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar detalle de pedido: {str(e)}"}), 500


# ===== TABLAS SECUNDARIAS - DETALLES COMPRA - COMPLETAR CRUD =====
@main_bp.route('/detalle-compra', methods=['GET'])
def get_detalles_compra():
    try:
        detalles = DetalleCompra.query.all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": "Error al obtener detalles de compra"}), 500

@main_bp.route('/detalle-compra', methods=['POST'])
def create_detalle_compra():
    try:
        data = request.get_json()
        required_fields = ['compra_id', 'producto_id', 'cantidad', 'precio_unidad']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        detalle = DetalleCompra(
            compra_id=data['compra_id'],
            producto_id=data['producto_id'],
            cantidad=data['cantidad'],
            precio_unidad=float(data['precio_unidad']),
            subtotal=float(data['cantidad']) * float(data['precio_unidad'])
        )
        db.session.add(detalle)
        db.session.commit()
        return jsonify({"message": "Detalle de compra creado", "detalle": detalle.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear detalle de compra"}), 500

@main_bp.route('/detalle-compra/<int:id>', methods=['PUT'])
def update_detalle_compra(id):
    try:
        detalle = DetalleCompra.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de compra no encontrado"}), 404

        data = request.get_json()
        if 'compra_id' in data:
            detalle.compra_id = data['compra_id']
        if 'producto_id' in data:
            detalle.producto_id = data['producto_id']
        if 'cantidad' in data:
            detalle.cantidad = data['cantidad']
        if 'precio_unidad' in data:
            detalle.precio_unidad = float(data['precio_unidad'])
        if 'cantidad' in data and 'precio_unidad' in data:
            detalle.subtotal = float(data['cantidad']) * float(data['precio_unidad'])

        db.session.commit()
        return jsonify({"message": "Detalle de compra actualizado", "detalle": detalle.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar detalle de compra"}), 500

@main_bp.route('/detalle-compra/<int:id>', methods=['DELETE'])
def delete_detalle_compra(id):
    try:
        detalle = DetalleCompra.query.get(id)
        if not detalle:
            return jsonify({"error": "Detalle de compra no encontrado"}), 404

        db.session.delete(detalle)
        db.session.commit()
        return jsonify({"message": "Detalle de compra eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar detalle de compra"}), 500

# ===== TABLAS MAESTRAS - ESTADO CITA - COMPLETAR CRUD =====
@main_bp.route('/estado-cita', methods=['GET'])
def get_estados_cita():
    try:
        estados = EstadoCita.query.all()
        return jsonify([estado.to_dict() for estado in estados])
    except Exception as e:
        return jsonify({"error": "Error al obtener estados de cita"}), 500

@main_bp.route('/estado-cita', methods=['POST'])
def create_estado_cita():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400

        estado = EstadoCita(nombre=data['nombre'])
        db.session.add(estado)
        db.session.commit()
        return jsonify({"message": "Estado de cita creado", "estado": estado.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear estado de cita"}), 500

@main_bp.route('/estado-cita/<int:id>', methods=['PUT'])
def update_estado_cita(id):
    try:
        estado = EstadoCita.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de cita no encontrado"}), 404

        data = request.get_json()
        if 'nombre' in data:
            estado.nombre = data['nombre']

        db.session.commit()
        return jsonify({"message": "Estado de cita actualizado", "estado": estado.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar estado de cita"}), 500

@main_bp.route('/estado-cita/<int:id>', methods=['DELETE'])
def delete_estado_cita(id):
    try:
        estado = EstadoCita.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de cita no encontrado"}), 404

        db.session.delete(estado)
        db.session.commit()
        return jsonify({"message": "Estado de cita eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar estado de cita"}), 500

# ===== TABLAS MAESTRAS - ESTADO VENTA - COMPLETAR CRUD =====
@main_bp.route('/estado-venta', methods=['GET'])
def get_estados_venta():
    try:
        estados = EstadoVenta.query.all()
        return jsonify([estado.to_dict() for estado in estados])
    except Exception as e:
        return jsonify({"error": "Error al obtener estados de venta"}), 500

@main_bp.route('/estado-venta', methods=['POST'])
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
def delete_estado_venta(id):
    try:
        estado = EstadoVenta.query.get(id)
        if not estado:
            return jsonify({"error": "Estado de venta no encontrado"}), 404

        db.session.delete(estado)
        db.session.commit()
        return jsonify({"message": "Estado de venta eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar estado de venta"}), 500

# ===== TABLAS DEL SISTEMA - HORARIO - COMPLETAR CRUD =====
@main_bp.route('/horario', methods=['GET'])
def get_horarios():
    try:
        # 👇 CAMBIO: Devuelve TODOS (activos e inactivos)
        horarios = Horario.query.all()
        return jsonify([horario.to_dict() for horario in horarios])
    except Exception as e:
        return jsonify({"error": "Error al obtener horarios"}), 500

@main_bp.route('/horario', methods=['POST'])
def create_horario():
    try:
        data = request.get_json()

        required_fields = ['empleado_id', 'hora_inicio', 'hora_final', 'dia']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Validar día (0-6)
        if not isinstance(data['dia'], int) or data['dia'] not in range(0, 7):
            return jsonify({"error": "El día debe ser un número entre 0 (lunes) y 6 (domingo)"}), 400

        hora_inicio = datetime.strptime(data['hora_inicio'], '%H:%M').time()
        hora_final = datetime.strptime(data['hora_final'], '%H:%M').time()

        # Validar rango horario
        if hora_final <= hora_inicio:
            return jsonify({"error": "La hora final debe ser mayor que la hora inicio"}), 400

        horario = Horario(
            empleado_id=data['empleado_id'],
            dia=data['dia'],
            hora_inicio=hora_inicio,
            hora_final=hora_final,
            activo=True
        )

        db.session.add(horario)
        db.session.commit()

        return jsonify({
            "message": "Horario creado",
            "horario": horario.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear horario"}), 500


@main_bp.route('/horario/<int:id>', methods=['PUT'])
def update_horario(id):
    try:
        horario = Horario.query.get(id)
        if not horario:
            return jsonify({"error": "Horario no encontrado"}), 404

        data = request.get_json()

        if 'empleado_id' in data:
            horario.empleado_id = data['empleado_id']

        if 'dia' in data:
            if not isinstance(data['dia'], int) or data['dia'] not in range(0, 7):
                return jsonify({"error": "El día debe ser un número entre 0 (lunes) y 6 (domingo)"}), 400
            horario.dia = data['dia']

        if 'hora_inicio' in data:
            horario.hora_inicio = datetime.strptime(data['hora_inicio'], '%H:%M').time()

        if 'hora_final' in data:
            horario.hora_final = datetime.strptime(data['hora_final'], '%H:%M').time()

        # 👇 NUEVO: Permitir actualizar estado por PUT
        if 'activo' in data:
            horario.activo = data['activo']

        # Validar que el rango siga siendo correcto
        if horario.hora_final <= horario.hora_inicio:
            return jsonify({"error": "La hora final debe ser mayor que la hora inicio"}), 400

        db.session.commit()

        return jsonify({
            "message": "Horario actualizado",
            "horario": horario.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar horario"}), 500


@main_bp.route('/horario/<int:id>', methods=['DELETE'])
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
        return jsonify({"error": "Error al eliminar horario"}), 500


@main_bp.route('/horario/empleado/<int:empleado_id>', methods=['GET'])
def get_horarios_por_empleado(empleado_id):
    try:
        # 👇 CAMBIO: Devuelve TODOS del empleado
        horarios = Horario.query.filter_by(
            empleado_id=empleado_id
        ).all()

        return jsonify([h.to_dict() for h in horarios])
    except Exception:
        return jsonify({"error": "Error al obtener horarios"}), 500


# ===== Verificación de disponibilidad =====

@main_bp.route('/verificar-disponibilidad', methods=['GET'])
def verificar_disponibilidad():
    """
    Verifica si un empleado está disponible en una fecha y hora específicas.
    Query params:
        empleado_id (int): ID del empleado
        fecha (str): YYYY-MM-DD
        hora (str): HH:MM
        duracion (int): duración en minutos (opcional, default=30)
        exclude_cita_id (int): ID de una cita a excluir (para edición)
    """
    try:
        # 1. Obtener parámetros
        empleado_id = request.args.get('empleado_id', type=int)
        fecha_str = request.args.get('fecha')
        hora_str = request.args.get('hora')
        duracion = request.args.get('duracion', default=30, type=int)
        exclude_cita_id = request.args.get('exclude_cita_id', type=int)

        # Validaciones
        if not empleado_id or not fecha_str or not hora_str:
            return jsonify({
                "disponible": False,
                "mensaje": "Faltan parámetros: empleado_id, fecha, hora"
            }), 400

        # Convertir fecha y hora
        try:
            fecha_date = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            hora_time = datetime.strptime(hora_str, '%H:%M').time()
        except ValueError:
            return jsonify({
                "disponible": False,
                "mensaje": "Formato de fecha u hora inválido"
            }), 400

        # 2. Verificar horario del empleado para ese día
        dia_semana = fecha_date.weekday()  # 0=lunes, 6=domingo (coincide con el modelo)

        horario = Horario.query.filter_by(
            empleado_id=empleado_id,
            dia=dia_semana,
            activo=True
        ).first()

        if not horario:
            return jsonify({
                "disponible": False,
                "mensaje": "El empleado no tiene horario asignado para este día"
            })

        # Verificar si la hora está dentro del horario laboral
        if hora_time < horario.hora_inicio or hora_time > horario.hora_final:
            return jsonify({
                "disponible": False,
                "mensaje": f"El empleado solo trabaja de {horario.hora_inicio.strftime('%H:%M')} a {horario.hora_final.strftime('%H:%M')}"
            })

        # 3. Verificar si ya tiene citas que se superpongan
        # Calcular el intervalo de tiempo solicitado
        inicio_solicitado = datetime.combine(fecha_date, hora_time)
        fin_solicitado = inicio_solicitado + timedelta(minutes=duracion)

        # Obtener todas las citas del empleado para esa fecha
        citas = Cita.query.filter(
            Cita.empleado_id == empleado_id,
            Cita.fecha == fecha_date
        ).all()

        for cita in citas:
            # Excluir la cita que estamos editando si se pasa el parámetro
            if exclude_cita_id and cita.id == exclude_cita_id:
                continue

            # Convertir cita a intervalo
            inicio_cita = datetime.combine(cita.fecha, cita.hora)
            fin_cita = inicio_cita + timedelta(minutes=cita.duracion or 30)  # Si no tiene duración, asumir 30

            # Verificar superposición
            if inicio_solicitado < fin_cita and fin_solicitado > inicio_cita:
                return jsonify({
                    "disponible": False,
                    "mensaje": f"El empleado ya tiene una cita programada desde las {cita.hora.strftime('%H:%M')} hasta las {fin_cita.strftime('%H:%M')}"
                })

        # 4. Si todo está bien
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
            "mensaje": f"Error al verificar disponibilidad: {str(e)}"
        }), 500


# ===== MÓDULO CAMPAÑAS DE SALUD =====

@main_bp.route('/campanas-salud', methods=['GET'])
def get_campanas_salud():
    """Lista todas las campañas de salud (array vacío si no hay)"""
    try:
        campanas = CampanaSalud.query.all()
        return jsonify([campana.to_dict() for campana in campanas])
    except Exception as e:
        return jsonify({"error": "Error al obtener campañas"}), 500


@main_bp.route('/campanas-salud/<int:id>', methods=['GET'])
def get_campana_salud(id):
    """Obtiene una campaña de salud por su ID"""
    try:
        campana = CampanaSalud.query.get(id)
        if not campana:
            return jsonify({"error": "Campaña no encontrada"}), 404
        return jsonify(campana.to_dict())
    except Exception as e:
        return jsonify({"error": f"Error al obtener campaña: {str(e)}"}), 500


@main_bp.route('/campanas-salud', methods=['POST'])
def create_campana_salud():
    """
    Crea una nueva campaña de salud.
    - estado_cita_id es opcional: si no se envía, se asigna 2 (pendiente).
    - Se valida que el estado_cita_id exista en la tabla estado_cita.
    """
    try:
        data = request.get_json()
        required_fields = ['empleado_id', 'empresa', 'fecha', 'hora']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        # Obtener estado_cita_id (opcional, por defecto 2)
        estado_cita_id = data.get('estado_cita_id', 2)

        # Validar que el estado exista
        estado_cita = EstadoCita.query.get(estado_cita_id)
        if not estado_cita:
            return jsonify({"error": "El estado de cita especificado no existe"}), 400

        # Parsear fecha y hora
        try:
            fecha = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
            hora = datetime.strptime(data['hora'], '%H:%M').time()
        except ValueError:
            return jsonify({"error": "Formato de fecha (YYYY-MM-DD) u hora (HH:MM) inválido"}), 400

        campana = CampanaSalud(
            empleado_id=data['empleado_id'],
            empresa=data['empresa'],
            contacto=data.get('contacto'),
            fecha=fecha,
            hora=hora,
            direccion=data.get('direccion'),
            observaciones=data.get('observaciones'),
            estado_cita_id=estado_cita_id
        )
        db.session.add(campana)
        db.session.commit()
        return jsonify({"message": "Campaña creada", "campana": campana.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear campaña: {str(e)}"}), 500


@main_bp.route('/campanas-salud/<int:id>', methods=['PUT'])
def update_campana_salud(id):
    """Actualiza una campaña de salud existente"""
    try:
        campana = CampanaSalud.query.get(id)
        if not campana:
            return jsonify({"error": "Campaña no encontrada"}), 404

        data = request.get_json()

        if 'empleado_id' in data:
            campana.empleado_id = data['empleado_id']
        if 'empresa' in data:
            campana.empresa = data['empresa']
        if 'contacto' in data:
            campana.contacto = data['contacto']
        if 'fecha' in data:
            try:
                campana.fecha = datetime.strptime(data['fecha'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({"error": "Formato de fecha inválido (use YYYY-MM-DD)"}), 400
        if 'hora' in data:
            try:
                campana.hora = datetime.strptime(data['hora'], '%H:%M').time()
            except ValueError:
                return jsonify({"error": "Formato de hora inválido (use HH:MM)"}), 400
        if 'direccion' in data:
            campana.direccion = data['direccion']
        if 'observaciones' in data:
            campana.observaciones = data['observaciones']
        if 'estado_cita_id' in data:
            estado_cita = EstadoCita.query.get(data['estado_cita_id'])
            if not estado_cita:
                return jsonify({"error": "El estado de cita especificado no existe"}), 400
            campana.estado_cita_id = data['estado_cita_id']

        db.session.commit()
        return jsonify({"message": "Campaña actualizada", "campana": campana.to_dict()})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar campaña: {str(e)}"}), 500


@main_bp.route('/campanas-salud/<int:id>', methods=['DELETE'])
def delete_campana_salud(id):
    """Elimina una campaña de salud"""
    try:
        campana = CampanaSalud.query.get(id)
        if not campana:
            return jsonify({"error": "Campaña no encontrada"}), 404

        db.session.delete(campana)
        db.session.commit()
        return jsonify({"message": "Campaña eliminada correctamente"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar campaña: {str(e)}"}), 500


@main_bp.route('/empleados/<int:empleado_id>/campanas', methods=['GET'])
def get_campanas_por_empleado(empleado_id):
    """Lista todas las campañas de un empleado específico (array vacío si no tiene)"""
    try:
        campanas = CampanaSalud.query.filter_by(empleado_id=empleado_id).all()
        return jsonify([campana.to_dict() for campana in campanas])
    except Exception as e:
        return jsonify({"error": "Error al obtener campañas del empleado"}), 500

# ===== TABLAS DEL SISTEMA - HISTORIAL FORMULA - COMPLETAR CRUD =====
@main_bp.route('/historial-formula', methods=['GET'])
def get_historiales_formula():
    try:
        historiales = HistorialFormula.query.all()
        return jsonify([historial.to_dict() for historial in historiales])
    except Exception as e:
        return jsonify({"error": "Error al obtener historial de fórmulas"}), 500

@main_bp.route('/historial-formula', methods=['POST'])
def create_historial_formula():
    try:
        data = request.get_json()
        if not data.get('cliente_id'):
            return jsonify({"error": "El cliente_id es requerido"}), 400

        historial = HistorialFormula(
            cliente_id=data['cliente_id'],
            descripcion=data.get('descripcion', ''),
            od_esfera=data.get('od_esfera'),
            od_cilindro=data.get('od_cilindro'),
            od_eje=data.get('od_eje'),
            oi_esfera=data.get('oi_esfera'),
            oi_cilindro=data.get('oi_cilindro'),
            oi_eje=data.get('oi_eje')
        )
        db.session.add(historial)
        db.session.commit()
        return jsonify({"message": "Historial de fórmula creado", "historial": historial.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear historial de fórmula"}), 500

@main_bp.route('/historial-formula/<int:id>', methods=['PUT'])
def update_historial_formula(id):
    try:
        historial = HistorialFormula.query.get(id)
        if not historial:
            return jsonify({"error": "Historial de fórmula no encontrado"}), 404

        data = request.get_json()
        if 'cliente_id' in data:
            historial.cliente_id = data['cliente_id']
        if 'descripcion' in data:
            historial.descripcion = data['descripcion']
        if 'od_esfera' in data:
            historial.od_esfera = data['od_esfera']
        if 'od_cilindro' in data:
            historial.od_cilindro = data['od_cilindro']
        if 'od_eje' in data:
            historial.od_eje = data['od_eje']
        if 'oi_esfera' in data:
            historial.oi_esfera = data['oi_esfera']
        if 'oi_cilindro' in data:
            historial.oi_cilindro = data['oi_cilindro']
        if 'oi_eje' in data:
            historial.oi_eje = data['oi_eje']

        db.session.commit()
        return jsonify({"message": "Historial de fórmula actualizado", "historial": historial.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar historial de fórmula"}), 500

@main_bp.route('/historial-formula/<int:id>', methods=['DELETE'])
def delete_historial_formula(id):
    try:
        historial = HistorialFormula.query.get(id)
        if not historial:
            return jsonify({"error": "Historial de fórmula no encontrado"}), 404

        db.session.delete(historial)
        db.session.commit()
        return jsonify({"message": "Historial de fórmula eliminado correctamente"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al eliminar historial de fórmula"}), 500

#==============Abonos================#

@main_bp.route('/ventas/<int:venta_id>/abonos', methods=['POST'])
def add_abono(venta_id):
    """Registra un abono para una venta"""
    try:
        venta = Venta.query.get(venta_id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404

        data = request.get_json()
        if 'monto_abonado' not in data:
            return jsonify({"error": "El campo 'monto_abonado' es requerido"}), 400

        abono = Abono(
            venta_id=venta.id,
            monto_abonado=float(data['monto_abonado']),
            fecha=datetime.utcnow()
        )
        db.session.add(abono)
        db.session.commit()

        return jsonify({
            "message": "Abono registrado",
            "abono": abono.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al registrar abono: {str(e)}"}), 500


@main_bp.route('/ventas/<int:venta_id>/abonos', methods=['GET'])
def get_abonos(venta_id):
    """Obtiene todos los abonos de una venta"""
    try:
        venta = Venta.query.get(venta_id)
        if not venta:
            return jsonify({"error": "Venta no encontrada"}), 404

        abonos = Abono.query.filter_by(venta_id=venta_id).all()
        return jsonify([abono.to_dict() for abono in abonos])

    except Exception as e:
        return jsonify({"error": "Error al obtener abonos"}), 500


@main_bp.route('/abonos/<int:id>', methods=['DELETE'])
def delete_abono(id):
    """Elimina un abono (uso restringido, solo si es necesario)"""
    try:
        abono = Abono.query.get(id)
        if not abono:
            return jsonify({"error": "Abono no encontrado"}), 404

        db.session.delete(abono)
        db.session.commit()
        return jsonify({"message": "Abono eliminado"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar abono: {str(e)}"}), 500

# ===== TABLAS DE PERMISOS - PERMISO - COMPLETAR CRUD =====
@main_bp.route('/permiso', methods=['GET'])
def get_permisos():
    try:
        permisos = Permiso.query.all()
        return jsonify([permiso.to_dict() for permiso in permisos])
    except Exception as e:
        return jsonify({"error": "Error al obtener permisos"}), 500

@main_bp.route('/permiso', methods=['POST'])
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

# ===== MULTIMEDIA - SUPER SIMPLE =====

@main_bp.route('/multimedia', methods=['POST'])
def crear_multimedia():
    """Crear multimedia - Solo 2 campos requeridos: url y tipo"""
    try:
        data = request.get_json()
        
        if not data.get('url'):
            return jsonify({"error": "URL requerida"}), 400
        if not data.get('tipo'):
            return jsonify({"error": "Tipo requerido: 'categoria', 'comprobante' u 'otro'"}), 400
        
        # Validar tipo
        tipo = data['tipo']
        if tipo not in ['categoria', 'comprobante', 'otro']:
            return jsonify({"error": "Tipo debe ser: 'categoria', 'comprobante' u 'otro'"}), 400
        
        # Validaciones por tipo
        if tipo == 'categoria' and not data.get('categoria_id'):
            return jsonify({"error": "Para tipo 'categoria' se requiere categoria_id"}), 400
        
        if tipo == 'comprobante' and not data.get('pedido_id'):
            return jsonify({"error": "Para tipo 'comprobante' se requiere pedido_id"}), 400
        
        # Verificar que no exista ya (para categorías y comprobantes)
        if tipo == 'categoria':
            existente = Multimedia.query.filter_by(
                tipo='categoria', 
                categoria_id=data['categoria_id']
            ).first()
            if existente:
                # Actualizar URL existente
                existente.url = data['url']
                db.session.commit()
                return jsonify({
                    "success": True,
                    "message": "Imagen de categoría actualizada",
                    "multimedia": existente.to_dict()
                })
        
        if tipo == 'comprobante':
            existente = Multimedia.query.filter_by(
                tipo='comprobante',
                pedido_id=data['pedido_id']
            ).first()
            if existente:
                return jsonify({
                    "error": "Este pedido ya tiene un comprobante"
                }), 400
        
        # Crear nuevo
        multimedia = Multimedia(
            url=data['url'],
            tipo=tipo,
            categoria_id=data.get('categoria_id'),
            pedido_id=data.get('pedido_id')
        )
        
        db.session.add(multimedia)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "multimedia": multimedia.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@main_bp.route('/multimedia/<string:tipo>', methods=['GET'])
def obtener_multimedia_tipo(tipo):
    """Obtener multimedia por tipo"""
    try:
        if tipo not in ['categoria', 'comprobante', 'otro']:
            return jsonify({"error": "Tipo no válido"}), 400
        
        items = Multimedia.query.filter_by(tipo=tipo).all()
        return jsonify([item.to_dict() for item in items])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@main_bp.route('/multimedia/categoria/<int:categoria_id>', methods=['GET'])
def obtener_imagen_categoria(categoria_id):
    """Obtener imagen de una categoría específica"""
    try:
        imagen = Multimedia.query.filter_by(
            tipo='categoria', 
            categoria_id=categoria_id
        ).first()
        
        if not imagen:
            return jsonify({"imagen": None})
        
        return jsonify(imagen.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@main_bp.route('/multimedia/comprobante/pedido/<int:pedido_id>', methods=['GET'])
def obtener_comprobante_pedido(pedido_id):
    """Obtener comprobante de un pedido"""
    try:
        comprobante = Multimedia.query.filter_by(
            tipo='comprobante', 
            pedido_id=pedido_id
        ).first()
        
        if not comprobante:
            return jsonify({"comprobante": None})
        
        return jsonify(comprobante.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== ENDPOINT ÚTIL PARA FLUTTER =====

@main_bp.route('/categorias-con-imagen', methods=['GET'])
def categorias_con_imagen():
    """Todas las categorías CON su imagen (si tienen)"""
    try:
        categorias = CategoriaProducto.query.all()
        resultado = []
        
        for categoria in categorias:
            cat_dict = categoria.to_dict()
            
            # Buscar imagen
            imagen = Multimedia.query.filter_by(
                tipo='categoria',
                categoria_id=categoria.id
            ).first()
            
            cat_dict['imagen_url'] = imagen.url if imagen else None
            resultado.append(cat_dict)
        
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# ===== MULTIMEDIA - ENDPOINTS PUT Y DELETE =====
@main_bp.route('/multimedia/<int:id>', methods=['PUT'])
def actualizar_multimedia(id):
    """Actualizar un elemento multimedia existente"""
    try:
        multimedia = Multimedia.query.get(id)
        if not multimedia:
            return jsonify({"error": "Elemento multimedia no encontrado"}), 404
        
        data = request.get_json()
        
        # Validaciones básicas
        if not data:
            return jsonify({"error": "Datos requeridos"}), 400
        
        # Actualizar campos
        if 'url' in data:
            multimedia.url = data['url']
        
        if 'tipo' in data:
            # Validar tipo
            tipo = data['tipo']
            if tipo not in ['categoria', 'comprobante', 'otro']:
                return jsonify({"error": "Tipo debe ser: 'categoria', 'comprobante' u 'otro'"}), 400
            multimedia.tipo = tipo
        
        # Actualizar relaciones según tipo
        if multimedia.tipo == 'categoria':
            if 'categoria_id' in data:
                multimedia.categoria_id = data['categoria_id']
            # Limpiar otros campos
            multimedia.pedido_id = None
        
        elif multimedia.tipo == 'comprobante':
            if 'pedido_id' in data:
                multimedia.pedido_id = data['pedido_id']
            # Limpiar otros campos
            multimedia.categoria_id = None
        
        else:  # tipo 'otro'
            multimedia.categoria_id = None
            multimedia.pedido_id = None
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Multimedia actualizado correctamente",
            "multimedia": multimedia.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar multimedia: {str(e)}"}), 500

@main_bp.route('/multimedia/<int:id>', methods=['DELETE'])
def eliminar_multimedia(id):
    """Eliminar un elemento multimedia"""
    try:
        multimedia = Multimedia.query.get(id)
        if not multimedia:
            return jsonify({"error": "Elemento multimedia no encontrado"}), 404
        
        db.session.delete(multimedia)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Multimedia con ID {id} eliminado correctamente"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar multimedia: {str(e)}"}), 500

@main_bp.route('/multimedia', methods=['GET'])
def obtener_todo_multimedia():
    """Obtener TODO el contenido multimedia (adicional a los GET existentes)"""
    try:
        items = Multimedia.query.all()
        return jsonify([item.to_dict() for item in items])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== TABLAS DE PERMISOS - PERMISO POR ROL - COMPLETAR CRUD =====
@main_bp.route('/permiso-rol', methods=['GET'])
def get_permisos_rol():
    try:
        permisos_rol = PermisoPorRol.query.all()
        return jsonify([permiso.to_dict() for permiso in permisos_rol])
    except Exception as e:
        return jsonify({"error": "Error al obtener permisos por rol"}), 500

@main_bp.route('/permiso-rol', methods=['POST'])
def create_permiso_rol():
    try:
        data = request.get_json()
        required_fields = ['rol_id', 'permiso_id']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400

        permiso_rol = PermisoPorRol(
            rol_id=data['rol_id'],
            permiso_id=data['permiso_id']
        )
        db.session.add(permiso_rol)
        db.session.commit()
        return jsonify({"message": "Permiso por rol creado", "permiso_rol": permiso_rol.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al crear permiso por rol"}), 500

@main_bp.route('/permiso-rol/<int:id>', methods=['PUT'])
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

# ===== RUTAS PARA OBTENER UN ELEMENTO ESPECÍFICO =====
@main_bp.route('/<tabla>/<int:id>', methods=['GET'])
def get_elemento(tabla, id):
    try:
        modelos = {
            'productos': Producto,
            'clientes': Cliente,
            'empleados': Empleado,
            'proveedores': Proveedor,
            'ventas': Venta,
            'citas': Cita,
            'servicios': Servicio,
            'usuarios': Usuario,
            'marcas': Marca,
            'categorias': CategoriaProducto,
            'compras': Compra,
            'estado-cita': EstadoCita,
            'estado-venta': EstadoVenta,
            'roles': Rol,
            'detalle-venta': DetalleVenta,
            'detalle-compra': DetalleCompra,
            'horario': Horario,
            'historial-formula': HistorialFormula,
            'abono': Abono,
            'permiso': Permiso,
            'permiso-rol': PermisoPorRol,
            # NUEVAS TABLAS
            'pedidos': Pedido,
            'detalle-pedido': DetallePedido,
            'imagenes': Imagen
        }
        
        if tabla not in modelos:
            return jsonify({"error": "Tabla no encontrada"}), 404
            
        elemento = modelos[tabla].query.get(id)
        if not elemento:
            return jsonify({"error": f"{tabla[:-1]} no encontrado"}), 404
            
        return jsonify(elemento.to_dict())
    except Exception as e:
        return jsonify({"error": "Error al obtener elemento"}), 500

# ===== RUTAS DE RELACIONES =====
@main_bp.route('/ventas/<int:venta_id>/detalles', methods=['GET'])
def get_detalles_venta_especifica(venta_id):
    try:
        detalles = DetalleVenta.query.filter_by(venta_id=venta_id).all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": "Error al obtener detalles de la venta"}), 500

@main_bp.route('/compras/<int:compra_id>/detalles', methods=['GET'])
def get_detalles_compra_especifica(compra_id):
    try:
        detalles = DetalleCompra.query.filter_by(compra_id=compra_id).all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": "Error al obtener detalles de la compra"}), 500

@main_bp.route('/clientes/<int:cliente_id>/historial', methods=['GET'])
def get_historial_cliente(cliente_id):
    try:
        historiales = HistorialFormula.query.filter_by(cliente_id=cliente_id).all()
        return jsonify([historial.to_dict() for historial in historiales])
    except Exception as e:
        return jsonify({"error": "Error al obtener historial del cliente"}), 500

@main_bp.route('/empleados/<int:empleado_id>/horarios', methods=['GET'])
def get_horarios_empleado(empleado_id):
    try:
        horarios = Horario.query.filter_by(empleado_id=empleado_id).all()
        return jsonify([horario.to_dict() for horario in horarios])
    except Exception as e:
        return jsonify({"error": "Error al obtener horarios del empleado"}), 500

@main_bp.route('/pedidos/<int:pedido_id>/detalles', methods=['GET'])
def get_detalles_de_pedido(pedido_id):
    """Obtiene los detalles de un pedido específico"""
    try:
        detalles = DetallePedido.query.filter_by(pedido_id=pedido_id).all()
        return jsonify([detalle.to_dict() for detalle in detalles])
    except Exception as e:
        return jsonify({"error": "Error al obtener detalles del pedido"}), 500

# ===== ACTUALIZAR LA RUTA DE ENDPOINTS PARA INCLUIR PUT Y DELETE =====
@main_bp.route('/endpoints', methods=['GET'])
def get_all_endpoints():
    """Documentación ACTUALIZADA de endpoints REALES"""
    return jsonify({
        "modulos_principales": {
            "clientes": "GET/POST /clientes, PUT/DELETE /clientes/{id}",
            "empleados": "GET/POST /empleados, PUT/DELETE /empleados/{id}",
            "proveedores": "GET/POST /proveedores, PUT/DELETE /proveedores/{id}",
            "ventas": "GET/POST /ventas, PUT/DELETE /ventas/{id}",
            "citas": "GET/POST /citas, PUT/DELETE /citas/{id}",
            "servicios": "GET/POST /servicios, PUT/DELETE /servicios/{id}",
            "usuarios": "GET/POST /usuarios, PUT/DELETE /usuarios/{id}",
            
            # CATÁLOGO
            "productos": "GET/POST /productos, PUT/DELETE /productos/{id}",
            "marcas": "GET/POST /marcas, PUT/DELETE /marcas/{id}",
            "categorias": "GET/POST /categorias, PUT/DELETE /categorias/{id}",
            
            # PEDIDOS
            "pedidos": "GET/POST /pedidos, PUT/DELETE /pedidos/{id}, GET /pedidos/cliente/{id} (PUT también genera venta al entregar)",
            
            # IMÁGENES (¡NUEVOS Y FUNCIONALES!)
            "imagen": "POST /imagen - Crear imagen para producto",
            "imagenes_producto": "GET /imagen/producto/{id} - Imágenes de un producto",
            "productos_imagenes": "GET /productos-imagenes - Productos CON sus imágenes",
            "categorias_imagenes": "GET /categorias-con-imagenes - Categorías básicas",
            
            # OTROS
            "compras": "GET/POST /compras, PUT/DELETE /compras/{id}",
            "roles": "GET/POST /roles, PUT/DELETE /roles/{id}"
        },
        
        "modulos_secundarios": {
            "detalle_venta": "GET/POST /detalle-venta, PUT/DELETE /detalle-venta/{id}",
            "detalle_compra": "GET/POST /detalle-compra, PUT/DELETE /detalle-compra/{id}",
            "detalle_pedido": "GET /pedidos/{id}/detalles",
            "estado_cita": "GET/POST /estado-cita, PUT/DELETE /estado-cita/{id}",
            "estado_venta": "GET/POST /estado-venta, PUT/DELETE /estado-venta/{id}",
            "horario": "GET/POST /horario, PUT/DELETE /horario/{id}",
            "historial_formula": "GET/POST /historial-formula, PUT/DELETE /historial-formula/{id}",
            "abono": "GET/POST /abono, PUT/DELETE /abono/{id}",
            "permiso": "GET/POST /permiso, PUT/DELETE /permiso/{id}",
            "permiso_rol": "GET/POST /permiso-rol, PUT/DELETE /permiso-rol/{id}"
        },
        
        "relaciones": {
            "detalles_venta": "GET /ventas/{id}/detalles",
            "detalles_compra": "GET /compras/{id}/detalles",
            "detalles_pedido": "GET /pedidos/{id}/detalles",
            
            # RELACIONES DE IMÁGENES (funcionales)
            "imagenes_de_producto": "GET /imagen/producto/{id}",
            
            "historial_cliente": "GET /clientes/{id}/historial",
            "horarios_empleado": "GET /empleados/{id}/horarios"
        },
        
        "utilidades": {
            "dashboard": "GET /dashboard/estadisticas",
            "elemento_especifico": "GET /{tabla}/{id}",
            "todos_endpoints": "GET /endpoints",
            "status_imagenes": "GET /status-imagenes (diagnóstico)"
        },
        
        "notas_importantes": {
            "imagenes": "Sistema Cloudinary activo. POST /imagen requiere: url (Cloudinary) y producto_id",
            "productos_imagenes": "Devuelve productos CON array de imágenes e imagen_principal",
            "cloudinary": "URLs: https://res.cloudinary.com/drhhthuqq/image/upload/..."
        }
    })