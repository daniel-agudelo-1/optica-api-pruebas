import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ============================================================
    # 1. CONFIGURACIÓN CORS
    # ============================================================
    CORS(app,
        origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:5500",
            os.getenv('FRONTEND_URL', '*')
        ],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Cache-Control"],
        supports_credentials=True
    )

    # ============================================================
    # 2. BASE DE DATOS
    # ============================================================
    from app.database import init_db, db
    init_db(app)

    # ============================================================
    # 3. AUTENTICACIÓN (JWT)
    # ============================================================
    from app.auth import init_auth
    init_auth(app)

    # ============================================================
    # 4. REGISTRO DE BLUEPRINTS
    # ============================================================
    from app.routes import main_bp
    from app.auth.routes import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # ============================================================
    # 5. MIDDLEWARE GLOBAL DE AUTENTICACIÓN
    # ============================================================
    @app.before_request
    def verificar_autenticacion():
        # Permitir OPTIONS (preflight de CORS)
        if request.method == 'OPTIONS':
            response = jsonify({'status': 'ok'})
            response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Cache-Control'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            return response, 200

        # ========================================================
        # RUTAS PÚBLICAS - accesibles SIN token
        # ========================================================
        RUTAS_PUBLICAS = {
            # Auth
            'auth.login',
            'auth.register',
            'auth.verify_register',
            'auth.forgot_password',
            'auth.reset_password',

            # Clientes desde landing (público)
            'main.get_clientes_publico',
            'main.create_cliente_publico',
            'main.update_cliente_publico',
            'main.delete_cliente_publico',

            # Catálogo landing
            'main.get_productos',
            'main.get_categorias',
            'main.get_marcas',
            'main.get_servicios',

            # Imágenes y multimedia públicas
            'main.get_imagenes',
            'main.get_imagen',
            'main.get_imagenes_por_producto',
            'main.obtener_comprobante_pedido',

            # Agendamiento desde landing (solo consulta)
            'main.get_estados_cita',
            'main.verificar_disponibilidad',
            'main.verificar_disponibilidad_multiple',

            # Utilidades
            'static',
            'main.home',
            'main.get_all_endpoints',
            'main.get_elemento',
        }

        # Si es ruta pública, permitir acceso
        if not request.endpoint or request.endpoint in RUTAS_PUBLICAS:
            return None

        # ========================================================
        # RUTAS PROTEGIDAS - requieren JWT (citas, perfil)
        # ========================================================
        RUTAS_PROTEGIDAS = {
            'main.agendar_cita',
            'main.get_mis_citas',
            'main.cancelar_mi_cita',
            'main.get_mi_perfil',
            'main.update_mi_perfil',
            'main.cambiar_mi_contrasenia',
        }

        from flask_jwt_extended import verify_jwt_in_request, get_jwt

        if request.endpoint in RUTAS_PROTEGIDAS:
            try:
                verify_jwt_in_request()
                return None
            except Exception:
                return jsonify({
                    "success": False,
                    "error": "Debes iniciar sesión",
                    "message": "Debes iniciar sesión para realizar esta acción",
                    "redirect": "/login"
                }), 401

        # ========================================================
        # RUTAS ADMIN - Solo empleados con rol
        # ========================================================
        if request.path.startswith('/admin/') or (request.endpoint and 'admin' in request.endpoint):
            try:
                verify_jwt_in_request()
                claims = get_jwt()
                
                # Cliente no puede acceder a rutas admin
                if claims.get('es_cliente', True):
                    return jsonify({
                        "success": False,
                        "error": "Acceso denegado",
                        "message": "Los clientes no tienen acceso al panel administrativo"
                    }), 403
                return None
            except Exception:
                return jsonify({
                    "success": False,
                    "error": "Token inválido",
                    "message": "Debes iniciar sesión para acceder a este recurso"
                }), 401

        # ========================================================
        # POR DEFECTO - requiere token
        # ========================================================
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({
                "success": False,
                "error": "Autenticación requerida",
                "message": "Debes iniciar sesión para acceder a este recurso"
            }), 401

    # ============================================================
    # 6. MANEJADORES DE ERRORES GLOBALES
    # ============================================================
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "success": False,
            "error": "Recurso no encontrado",
            "message": "La ruta solicitada no existe"
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            "success": False,
            "error": "Método no permitido",
            "message": "El método HTTP no está permitido para esta ruta"
        }), 405

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            "success": False,
            "error": "Error interno del servidor",
            "message": "Ocurrió un error inesperado. Intenta de nuevo más tarde"
        }), 500

    # ============================================================
    # 7. VERIFICACIÓN DE BASE DE DATOS AL INICIAR
    # ============================================================
    with app.app_context():
        try:
            db.create_all()
            print("✅ Base de datos conectada y estructura verificada")
        except Exception as e:
            print(f"⚠️ Error al conectar con la base de datos: {e}")

    return app