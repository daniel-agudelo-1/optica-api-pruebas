from flask import jsonify, request
from app.database import db
from app.Models.models import Marca, CategoriaProducto, Producto, Imagen, Multimedia
from app.routes import main_bp
from app.auth.decorators import permiso_requerido


# ============================================================
# MÓDULO: MARCAS
# ============================================================

@main_bp.route('/marcas', methods=['GET'])
def get_marcas():
    try:
        marcas = Marca.query.order_by(Marca.nombre.asc()).all()
        return jsonify([marca.to_dict() for marca in marcas])
    except Exception as e:
        return jsonify({"error": "Error al obtener marcas"}), 500


@main_bp.route('/marcas', methods=['POST'])
@permiso_requerido("productos")
def create_marca():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400
        
        nombre = " ".join(data['nombre'].split()).strip()
        
        if len(nombre) < 2:
            return jsonify({"error": "El nombre de la marca es demasiado corto"}), 400
        
        if Marca.query.filter(Marca.nombre.ilike(nombre)).first():
            return jsonify({"error": f"La marca '{nombre}' ya existe en el sistema"}), 400
        
        marca = Marca(
            nombre=nombre,
            estado=data.get('estado', True)
        )
        db.session.add(marca)
        db.session.commit()
        return jsonify({"message": "Marca creada", "marca": marca.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear marca: {str(e)}"}), 500


@main_bp.route('/marcas/<int:id>', methods=['PUT'])
@permiso_requerido("productos")
def update_marca(id):
    try:
        marca = Marca.query.get(id)
        if not marca:
            return jsonify({"error": "Marca no encontrada"}), 404
            
        data = request.get_json()
        
        if 'nombre' in data:
            nombre = " ".join(data['nombre'].split()).strip()
            
            if Marca.query.filter(Marca.nombre.ilike(nombre), Marca.id != id).first():
                return jsonify({"error": "Ya existe otra marca con este nombre"}), 400
            marca.nombre = nombre
            
        if 'estado' in data:
            # ✅ Cambio: Permitir cambiar estado siempre, sin importar productos
            marca.estado = data['estado']
            
        db.session.commit()
        return jsonify({"message": "Marca actualizada", "marca": marca.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar marca: {str(e)}"}), 500


@main_bp.route('/marcas/<int:id>', methods=['DELETE'])
@permiso_requerido("productos")
def delete_marca(id):
    try:
        marca = Marca.query.get(id)
        if not marca:
            return jsonify({"error": "Marca no encontrada"}), 404
        
        if marca.productos and len(marca.productos) > 0:
            return jsonify({
                "error": f"No se puede eliminar '{marca.nombre}' porque está vinculada a {len(marca.productos)} productos. Desactívela en su lugar."
            }), 400
            
        db.session.delete(marca)
        db.session.commit()
        return jsonify({"message": "Marca eliminada correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar marca: {str(e)}"}), 500


# ============================================================
# MÓDULO: CATEGORÍAS
# ============================================================

@main_bp.route('/categorias', methods=['GET'])
def get_categorias():
    try:
        categorias = CategoriaProducto.query.all()
        return jsonify([categoria.to_dict() for categoria in categorias])
    except Exception as e:
        return jsonify({"error": "Error al obtener categorías"}), 500


@main_bp.route('/categorias', methods=['POST'])
@permiso_requerido("productos")
def create_categoria():
    try:
        data = request.get_json()
        if not data.get('nombre'):
            return jsonify({"error": "El nombre es requerido"}), 400
        
        nombre = " ".join(data['nombre'].split()).strip()
        
        if not nombre:
            return jsonify({"error": "El nombre de categoría es obligatorio"}), 400
        
        if CategoriaProducto.query.filter(CategoriaProducto.nombre.ilike(nombre)).first():
            return jsonify({"error": "Esta categoría ya existe"}), 400
        
        categoria = CategoriaProducto(
            nombre=nombre,
            descripcion=data.get('descripcion', ''),
            estado=data.get('estado', True)
        )
        db.session.add(categoria)
        db.session.commit()
        return jsonify({"message": "Categoría creada", "categoria": categoria.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear categoría: {str(e)}"}), 500


@main_bp.route('/categorias/<int:id>', methods=['PUT'])
@permiso_requerido("productos")
def update_categoria(id):
    try:
        categoria = CategoriaProducto.query.get(id)
        if not categoria:
            return jsonify({"error": "Categoría no encontrada"}), 404
            
        data = request.get_json()
        
        if 'nombre' in data:
            nombre = " ".join(data['nombre'].split()).strip()
            
            existente = CategoriaProducto.query.filter(
                CategoriaProducto.nombre.ilike(nombre), 
                CategoriaProducto.id != id
            ).first()
            if existente:
                return jsonify({"error": "Ya existe otra categoría con ese nombre"}), 400
            categoria.nombre = nombre
            
        if 'descripcion' in data:
            categoria.descripcion = data['descripcion']
            
        if 'estado' in data:
            # ✅ Cambio: Permitir cambiar estado siempre, sin importar productos
            categoria.estado = data['estado']
            
        db.session.commit()
        return jsonify({"message": "Categoría actualizada", "categoria": categoria.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar categoría: {str(e)}"}), 500


@main_bp.route('/categorias/<int:id>', methods=['DELETE'])
@permiso_requerido("productos")
def delete_categoria(id):
    try:
        categoria = CategoriaProducto.query.get(id)
        if not categoria:
            return jsonify({"error": "Categoría no encontrada"}), 404
        
        if categoria.productos and len(categoria.productos) > 0:
            return jsonify({
                "error": f"No se puede eliminar. La categoría tiene {len(categoria.productos)} productos asignados. Desactívela en su lugar."
            }), 400
            
        db.session.delete(categoria)
        db.session.commit()
        return jsonify({"message": "Categoría eliminada correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar categoría: {str(e)}"}), 500


# ============================================================
# MÓDULO: PRODUCTOS
# ============================================================

@main_bp.route('/productos', methods=['GET'])
def get_productos():
    try:
        productos = Producto.query.order_by(Producto.nombre.asc()).all()
        return jsonify([producto.to_dict() for producto in productos])
    except Exception as e:
        return jsonify({"error": "Error al obtener productos"}), 500


@main_bp.route('/productos', methods=['POST'])
@permiso_requerido("productos")
def create_producto():
    try:
        data = request.get_json()
        required_fields = ['nombre', 'precio_venta', 'precio_compra', 'categoria_id', 'marca_id']
        
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"El campo {field} es requerido"}), 400
        
        p_venta = float(data['precio_venta'])
        p_compra = float(data['precio_compra'])
        
        if p_venta < 0:
            return jsonify({"error": "El precio de venta debe ser mayor a 0"}), 400
        if p_compra < 0:
            return jsonify({"error": "El precio de compra debe ser mayor a 0"}), 400
        if p_venta < p_compra:
            return jsonify({"error": "El precio de venta no puede ser menor al precio de compra"}), 400
        
        marca = Marca.query.get(data['marca_id'])
        categoria = CategoriaProducto.query.get(data['categoria_id'])
        
        if not marca:
            return jsonify({"error": "La marca seleccionada no existe"}), 400
        if not categoria:
            return jsonify({"error": "La categoría seleccionada no existe"}), 400
        if not marca.estado:
            return jsonify({"error": "No puedes crear productos con una marca inactiva"}), 400
        if not categoria.estado:
            return jsonify({"error": "No puedes crear productos con una categoría inactiva"}), 400
        
        stock = int(data.get('stock', 0))
        if stock < 0:
            return jsonify({"error": "El stock inicial no puede ser negativo"}), 400
        
        if Producto.query.filter(Producto.nombre.ilike(data['nombre'].strip())).first():
            return jsonify({"error": "Ya existe un producto con este nombre"}), 400
        
        producto = Producto(
            nombre=data['nombre'].strip(),
            precio_venta=p_venta,
            precio_compra=p_compra,
            stock=stock,
            stock_minimo=data.get('stock_minimo', 5),
            descripcion=data.get('descripcion', ''),
            categoria_producto_id=data['categoria_id'],
            marca_id=data['marca_id'],
            estado=data.get('estado', True)
        )
        
        db.session.add(producto)
        db.session.commit()
        return jsonify({"message": "Producto creado", "producto": producto.to_dict()}), 201
        
    except ValueError:
        return jsonify({"error": "Los precios y stock deben ser números válidos"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear producto: {str(e)}"}), 500


@main_bp.route('/productos/<int:id>', methods=['PUT'])
@permiso_requerido("productos")
def update_producto(id):
    try:
        producto = Producto.query.get(id)
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404
            
        data = request.get_json()
        
        if 'precio_venta' in data or 'precio_compra' in data:
            nuevo_pv = float(data.get('precio_venta', producto.precio_venta))
            nuevo_pc = float(data.get('precio_compra', producto.precio_compra))
            
            if nuevo_pv < 0:
                return jsonify({"error": "El precio de venta debe ser mayor a 0"}), 400
            if nuevo_pc < 0:
                return jsonify({"error": "El precio de compra debe ser mayor a 0"}), 400
            if nuevo_pv < nuevo_pc:
                return jsonify({"error": "El precio de venta no puede ser menor al precio de compra"}), 400
                
            producto.precio_venta = nuevo_pv
            producto.precio_compra = nuevo_pc
        
        if 'stock' in data:
            nuevo_stock = int(data['stock'])
            if nuevo_stock < 0:
                return jsonify({"error": "El stock no puede ser negativo"}), 400
            producto.stock = nuevo_stock
            
        if 'stock_minimo' in data:
            nuevo_minimo = int(data['stock_minimo'])
            if nuevo_minimo < 0:
                return jsonify({"error": "El stock mínimo no puede ser negativo"}), 400
            producto.stock_minimo = nuevo_minimo
        
        if 'categoria_id' in data:
            categoria = CategoriaProducto.query.get(data['categoria_id'])
            if not categoria:
                return jsonify({"error": "La categoría no existe"}), 400
            if not categoria.estado:
                return jsonify({"error": "No puedes asignar una categoría inactiva"}), 400
            producto.categoria_producto_id = data['categoria_id']
        
        if 'marca_id' in data:
            marca = Marca.query.get(data['marca_id'])
            if not marca:
                return jsonify({"error": "La marca no existe"}), 400
            if not marca.estado:
                return jsonify({"error": "No puedes asignar una marca inactiva"}), 400
            producto.marca_id = data['marca_id']
        
        if 'estado' in data:
            # ✅ Cambio: Permitir cambiar estado siempre
            producto.estado = data['estado']
        
        if 'nombre' in data:
            nombre = data['nombre'].strip()
            if Producto.query.filter(Producto.nombre.ilike(nombre), Producto.id != id).first():
                return jsonify({"error": "Ya existe otro producto con este nombre"}), 400
            producto.nombre = nombre
            
        if 'descripcion' in data:
            producto.descripcion = data['descripcion']
        
        db.session.commit()
        return jsonify({"message": "Producto actualizado", "producto": producto.to_dict()})
        
    except ValueError:
        return jsonify({"error": "Los precios y stock deben ser números válidos"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar producto: {str(e)}"}), 500


@main_bp.route('/productos/<int:id>', methods=['DELETE'])
@permiso_requerido("productos")
def delete_producto(id):
    try:
        producto = Producto.query.get(id)
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404
        
        if producto.detalle_ventas and len(producto.detalle_ventas) > 0:
            return jsonify({"error": "No se puede eliminar un producto que tiene ventas asociadas"}), 400
        
        db.session.delete(producto)
        db.session.commit()
        return jsonify({"message": "Producto eliminado correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar producto: {str(e)}"}), 500


# ============================================================
# MÓDULO: IMÁGENES
# ============================================================

@main_bp.route('/imagenes', methods=['POST'])
@permiso_requerido("productos")
def crear_imagen():
    try:
        data = request.get_json()
        if not data or not data.get('url') or not data.get('producto_id'):
            return jsonify({"error": "url y producto_id requeridos"}), 400
            
        producto = Producto.query.get(data['producto_id'])
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404
            
        if not producto.estado:
            return jsonify({"error": "No puedes agregar imágenes a un producto inactivo"}), 400
            
        imagen = Imagen(url=data['url'], producto_id=data['producto_id'])
        db.session.add(imagen)
        db.session.commit()
        return jsonify({"message": "Imagen creada", "imagen": imagen.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@main_bp.route('/imagenes', methods=['GET'])
def get_imagenes():
    try:
        imagenes = Imagen.query.all()
        return jsonify([img.to_dict() for img in imagenes])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main_bp.route('/imagenes/<int:id>', methods=['GET'])
def get_imagen(id):
    try:
        imagen = Imagen.query.get(id)
        if not imagen:
            return jsonify({"error": "Imagen no encontrada"}), 404
        return jsonify(imagen.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main_bp.route('/imagenes/producto/<int:producto_id>', methods=['GET'])
def get_imagenes_por_producto(producto_id):
    try:
        producto = Producto.query.get(producto_id)
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404
        return jsonify({"producto_id": producto_id, "imagenes": [img.to_dict() for img in producto.imagenes]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main_bp.route('/imagenes/<int:id>', methods=['PUT'])
@permiso_requerido("productos")
def update_imagen(id):
    try:
        imagen = Imagen.query.get(id)
        if not imagen:
            return jsonify({"error": "Imagen no encontrada"}), 404
            
        data = request.get_json()
        
        if 'url' in data:
            if not data['url']:
                return jsonify({"error": "La URL no puede estar vacía"}), 400
            imagen.url = data['url']
            
        if 'producto_id' in data:
            producto = Producto.query.get(data['producto_id'])
            if not producto:
                return jsonify({"error": "Producto no encontrado"}), 404
            if not producto.estado:
                return jsonify({"error": "No puedes asignar la imagen a un producto inactivo"}), 400
            imagen.producto_id = data['producto_id']
            
        db.session.commit()
        return jsonify({"message": "Imagen actualizada", "imagen": imagen.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@main_bp.route('/imagenes/<int:id>', methods=['DELETE'])
@permiso_requerido("productos")
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


# ============================================================
# MÓDULO: MULTIMEDIA
# ============================================================

@main_bp.route('/multimedia', methods=['POST'])
@permiso_requerido("productos")
def crear_multimedia():
    try:
        data = request.get_json()
        
        if not data.get('url'):
            return jsonify({"error": "URL requerida"}), 400
        if not data.get('tipo'):
            return jsonify({"error": "Tipo requerido: 'categoria', 'comprobante' u 'otro'"}), 400
            
        tipo = data['tipo']
        if tipo not in ['categoria', 'comprobante', 'otro']:
            return jsonify({"error": "Tipo debe ser: 'categoria', 'comprobante' u 'otro'"}), 400
            
        if tipo == 'categoria':
            if not data.get('categoria_id'):
                return jsonify({"error": "Para tipo 'categoria' se requiere categoria_id"}), 400
                
            categoria = CategoriaProducto.query.get(data['categoria_id'])
            if not categoria:
                return jsonify({"error": "La categoría especificada no existe"}), 404
                
            existente = Multimedia.query.filter_by(tipo='categoria', categoria_id=data['categoria_id']).first()
            if existente:
                existente.url = data['url']
                db.session.commit()
                return jsonify({"success": True, "message": "Imagen de categoría actualizada", "multimedia": existente.to_dict()})
                
        if tipo == 'comprobante':
            if not data.get('pedido_id'):
                return jsonify({"error": "Para tipo 'comprobante' se requiere pedido_id"}), 400
            
            from app.Models.models import Pedido
            
            pedido = Pedido.query.get(data['pedido_id'])
            if not pedido:
                return jsonify({"error": "El pedido especificado no existe"}), 404
                
            existente = Multimedia.query.filter_by(tipo='comprobante', pedido_id=data['pedido_id']).first()
            if existente:
                return jsonify({"error": "Este pedido ya tiene un comprobante"}), 400
                
        multimedia = Multimedia(
            url=data['url'], 
            tipo=tipo, 
            categoria_id=data.get('categoria_id'), 
            pedido_id=data.get('pedido_id')
        )
        db.session.add(multimedia)
        db.session.commit()
        return jsonify({"success": True, "multimedia": multimedia.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@main_bp.route('/multimedia/comprobante/pedido/<int:pedido_id>', methods=['GET'])
def obtener_comprobante_pedido(pedido_id):
    try:
        from app.Models.models import Pedido
        
        pedido = Pedido.query.get(pedido_id)
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404
            
        comprobante = Multimedia.query.filter_by(tipo='comprobante', pedido_id=pedido_id).first()
        if not comprobante:
            return jsonify({"comprobante": None})
        return jsonify(comprobante.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main_bp.route('/multimedia/<int:id>', methods=['PUT'])
@permiso_requerido("productos")
def actualizar_multimedia(id):
    try:
        multimedia = Multimedia.query.get(id)
        if not multimedia:
            return jsonify({"error": "Elemento multimedia no encontrado"}), 404
            
        data = request.get_json()
        
        if 'url' in data:
            if not data['url']:
                return jsonify({"error": "La URL no puede estar vacía"}), 400
            multimedia.url = data['url']
            
        if 'tipo' in data:
            tipo = data['tipo']
            if tipo not in ['categoria', 'comprobante', 'otro']:
                return jsonify({"error": "Tipo debe ser: 'categoria', 'comprobante' u 'otro'"}), 400
            multimedia.tipo = tipo
            
        if multimedia.tipo == 'categoria':
            if 'categoria_id' in data:
                categoria = CategoriaProducto.query.get(data['categoria_id'])
                if not categoria:
                    return jsonify({"error": "La categoría no existe"}), 404
                multimedia.categoria_id = data['categoria_id']
            multimedia.pedido_id = None
            
        elif multimedia.tipo == 'comprobante':
            if 'pedido_id' in data:
                from app.Models.models import Pedido
                pedido = Pedido.query.get(data['pedido_id'])
                if not pedido:
                    return jsonify({"error": "El pedido no existe"}), 404
                multimedia.pedido_id = data['pedido_id']
            multimedia.categoria_id = None
            
        else:
            multimedia.categoria_id = None
            multimedia.pedido_id = None
            
        db.session.commit()
        return jsonify({"success": True, "message": "Multimedia actualizado", "multimedia": multimedia.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500