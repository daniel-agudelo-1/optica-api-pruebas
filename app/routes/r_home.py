from flask import jsonify, request
from app.routes import main_bp
from app.Models.models import (
    Producto, Cliente, Empleado, Proveedor, Venta, Cita, Servicio, Usuario,
    Marca, CategoriaProducto, Compra, EstadoCita, EstadoVenta, Rol,
    DetalleVenta, DetalleCompra, Horario, HistorialFormula, Abono,
    Permiso, PermisoPorRol, Pedido, DetallePedido, Imagen, CampanaSalud
)

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
            "pedidos": "GET/POST /pedidos, /pedidos/cliente/{id}"
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
            "productos": "GET/POST /productos, PUT/DELETE /productos/{id}",
            "marcas": "GET/POST /marcas, PUT/DELETE /marcas/{id}",
            "categorias": "GET/POST /categorias, PUT/DELETE /categorias/{id}",
            "pedidos": "GET/POST /pedidos, PUT/DELETE /pedidos/{id}, GET /pedidos/cliente/{id}",
            "imagenes": "GET/POST /imagenes, PUT/DELETE /imagenes/{id}",
            "compras": "GET/POST /compras, PUT/DELETE /compras/{id}",
            "roles": "GET/POST /roles, PUT/DELETE /roles/{id}"
        },
        "modulos_secundarios": {
            "detalle_venta": "GET/POST /detalle-venta, PUT/DELETE /detalle-venta/{id}",
            "detalle_compra": "GET/POST /detalle-compra, PUT/DELETE /detalle-compra/{id}",
            "detalle_pedido": "GET /pedidos/{id}/detalles, POST/PUT/DELETE /detalle-pedido",
            "estado_cita": "GET/POST /estado-cita, PUT/DELETE /estado-cita/{id}",
            "estado_venta": "GET/POST /estado-venta, PUT/DELETE /estado-venta/{id}",
            "horario": "GET/POST /horario, PUT/DELETE /horario/{id}",
            "historial_formula": "GET/POST /historial-formula, PUT/DELETE /historial-formula/{id}",
            "abono": "GET/POST /abono, PUT/DELETE /abono/{id}",
            "permiso": "GET/POST /permiso, PUT/DELETE /permiso/{id}",
            "permiso_rol": "GET/POST /permiso-rol, PUT/DELETE /permiso-rol/{id}",
            "multimedia": "GET/POST /multimedia, PUT/DELETE /multimedia/{id}"
        },
        "relaciones": {
            "detalles_venta": "GET /ventas/{id}/detalles",
            "detalles_compra": "GET /compras/{id}/detalles",
            "detalles_pedido": "GET /pedidos/{id}/detalles",
            "historial_cliente": "GET /clientes/{id}/historial",
            "horarios_empleado": "GET /empleados/{id}/horarios",
            "categorias_con_imagen": "GET /categorias-con-imagen"
        },
        "utilidades": {
            "elemento_especifico": "GET /{tabla}/{id}",
            "todos_endpoints": "GET /endpoints",
            "verificar_disponibilidad": "GET /verificar-disponibilidad"
        }
    })

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
            'pedidos': Pedido,
            'detalle-pedido': DetallePedido,
            'imagenes': Imagen,
            'campanas-salud': CampanaSalud
        }
        
        if tabla not in modelos:
            return jsonify({"error": "Tabla no encontrada"}), 404
            
        elemento = modelos[tabla].query.get(id)
        if not elemento:
            return jsonify({"error": f"{tabla[:-1]} no encontrado"}), 404
            
        return jsonify(elemento.to_dict())
    except Exception as e:
        return jsonify({"error": "Error al obtener elemento"}), 500