from app.database import db
from datetime import datetime

# ============================================================
# TABLAS DE ROLES Y USUARIOS
# ============================================================

class Rol(db.Model):
    __tablename__ = 'rol'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    descripcion = db.Column(db.String(200))
    estado = db.Column(db.Boolean, default=True)
    usuarios = db.relationship('Usuario', backref='rol', lazy=True)
    permisos = db.relationship(
        'Permiso',
        secondary='permiso_por_rol',
        lazy=True
    )

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'permisos': [p.to_dict() for p in self.permisos],
            'estado': self.estado
        }


class Usuario(db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    correo = db.Column(db.String(100), nullable=False, unique=True)
    contrasenia = db.Column(db.String(255), nullable=False)
    rol_id = db.Column(db.Integer, db.ForeignKey('rol.id'), nullable=True)
    estado = db.Column(db.Boolean, default=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)

    nombre = db.Column(db.String(70))
    apellido = db.Column(db.String(70))   # ← agregado
    telefono = db.Column(db.String(20))
    tipo_documento = db.Column(db.String(20))
    numero_documento = db.Column(db.String(20))
    fecha_nacimiento = db.Column(db.Date)

    cliente = db.relationship('Cliente', backref=db.backref('usuario', uselist=False), lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'correo': self.correo,
            'rol_id': self.rol_id,
            'rol_nombre': self.rol.nombre if self.rol else None,
            'estado': self.estado,
            'cliente_id': self.cliente_id,
            'nombre': self.nombre,
            'apellido': self.apellido,
            'telefono': self.telefono,
            'tipo_documento': self.tipo_documento,
            'numero_documento': self.numero_documento,
            'fecha_nacimiento': self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None,
            'es_admin': (self.rol_id is not None and self.rol.nombre == 'Admin')
        }


class Permiso(db.Model):
    __tablename__ = 'permiso'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre
        }


class PermisoPorRol(db.Model):
    __tablename__ = 'permiso_por_rol'
    id = db.Column(db.Integer, primary_key=True)
    rol_id = db.Column(db.Integer, db.ForeignKey('rol.id'), nullable=False)
    permiso_id = db.Column(db.Integer, db.ForeignKey('permiso.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'rol_id': self.rol_id,
            'permiso_id': self.permiso_id
        }


# ============================================================
# TABLAS DE PRODUCTOS
# ============================================================

class Marca(db.Model):
    __tablename__ = 'marca'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    estado = db.Column(db.Boolean, default=True)  
    productos = db.relationship('Producto', backref='marca', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'estado': self.estado, 
        }


class Imagen(db.Model):
    __tablename__ = 'imagen'
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    producto = db.relationship('Producto', back_populates='imagenes')

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "producto_id": self.producto_id
        }


class CategoriaProducto(db.Model):
    __tablename__ = 'categoria_producto'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(500))
    estado = db.Column(db.Boolean, default=True)
    productos = db.relationship('Producto', backref='categoria', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'estado': self.estado,
        }


class Producto(db.Model):
    __tablename__ = 'producto'
    
    id = db.Column(db.Integer, primary_key=True)
    categoria_producto_id = db.Column(db.Integer, db.ForeignKey('categoria_producto.id'), nullable=False)
    marca_id = db.Column(db.Integer, db.ForeignKey('marca.id'), nullable=False)
    nombre = db.Column(db.String(50), nullable=False)
    precio_venta = db.Column(db.Float, nullable=False)
    precio_compra = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    stock_minimo = db.Column(db.Integer, default=0)
    descripcion = db.Column(db.String(500)) 
    estado = db.Column(db.Boolean, default=True)
    
    imagenes = db.relationship('Imagen', back_populates='producto', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'precio_venta': self.precio_venta,
            'precio_compra': self.precio_compra,
            'stock': self.stock,
            'stock_minimo': self.stock_minimo,
            'descripcion': self.descripcion,  
            'estado': self.estado,
            'categoria_id': self.categoria_producto_id,
            'marca_id': self.marca_id,
            'imagenes': [img.to_dict() for img in self.imagenes] if self.imagenes else []
        }


# ============================================================
# TABLA DE PEDIDOS
# ============================================================

class Pedido(db.Model):
    __tablename__ = 'pedido'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float, nullable=False)
    metodo_pago = db.Column(db.String(20))
    metodo_entrega = db.Column(db.String(20))
    direccion_entrega = db.Column(db.String(100))
    departamento_entrega = db.Column(db.String(50))
    municipio_entrega = db.Column(db.String(50))
    barrio_entrega = db.Column(db.String(50))
    codigo_postal_entrega = db.Column(db.String(10))
    transferencia_comprobante = db.Column(db.String(255))
    abono_acumulado = db.Column(db.Float, default=0.0)
    estado_id = db.Column(db.Integer, db.ForeignKey('estado_pedido.id'), nullable=False)
    estado = db.relationship('EstadoPedido', backref='pedidos')
    cliente = db.relationship('Cliente', backref='pedidos')
    items = db.relationship('DetallePedido', backref='pedido', lazy=True, cascade='all, delete-orphan')
    abonos = db.relationship('Abono', foreign_keys='Abono.pedido_id', backref='pedido', lazy=True)

    @property
    def saldo_pendiente(self):
        return self.total - (self.abono_acumulado or 0)

    def to_dict(self):
        return {
            'id': self.id,
            'cliente_id': self.cliente_id,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'total': self.total,
            'metodo_pago': self.metodo_pago,
            'metodo_entrega': self.metodo_entrega,
            'direccion_entrega': self.direccion_entrega,
            'departamento_entrega': self.departamento_entrega,
            'municipio_entrega': self.municipio_entrega,
            'barrio_entrega': self.barrio_entrega,
            'codigo_postal_entrega': self.codigo_postal_entrega,
            'transferencia_comprobante': self.transferencia_comprobante,
            'abono_acumulado': self.abono_acumulado,
            'saldo_pendiente': self.saldo_pendiente,
            'estado_id': self.estado_id,
            'estado_nombre': self.estado.nombre if self.estado else None,
            'cliente_nombre': self.cliente.nombre if self.cliente else None,
            'items': [item.to_dict() for item in self.items] if self.items else []
        }


class DetallePedido(db.Model):
    __tablename__ = 'detalle_pedido'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    producto = db.relationship('Producto', backref='detalle_pedidos')

    def to_dict(self):
        return {
            'id': self.id,
            'pedido_id': self.pedido_id,
            'producto_id': self.producto_id,
            'producto_nombre': self.producto.nombre if self.producto else None,
            'cantidad': self.cantidad,
            'precio_unitario': self.precio_unitario,
            'subtotal': self.subtotal
        }


class EstadoPedido(db.Model):
    __tablename__ = 'estado_pedido'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(20), nullable=False, unique=True)

    def to_dict(self):
        return {'id': self.id, 'nombre': self.nombre}


# ============================================================
# TABLA DE ABONO
# ============================================================

class Abono(db.Model):
    __tablename__ = 'abono'
    id = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    observacion = db.Column(db.String(255), nullable=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'monto': self.monto,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'observacion': self.observacion,
            'pedido_id': self.pedido_id,
            'venta_id': self.venta_id
        }


# ============================================================
# TABLAS DE PROVEEDORES Y COMPRAS
# ============================================================

class Proveedor(db.Model):
    __tablename__ = 'proveedor'
    id = db.Column(db.Integer, primary_key=True)
    tipo_proveedor = db.Column(db.String(20))
    tipo_documento = db.Column(db.String(4))
    documento = db.Column(db.String(20))
    razon_social_o_nombre = db.Column(db.String(30), nullable=False)
    contacto = db.Column(db.String(20))
    telefono = db.Column(db.String(10))
    correo = db.Column(db.String(50))
    departamento = db.Column(db.String(15))
    municipio = db.Column(db.String(15))
    direccion = db.Column(db.String(30))
    estado = db.Column(db.Boolean, default=True)
    compras = db.relationship('Compra', backref='proveedor', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'tipo_proveedor': self.tipo_proveedor,
            'tipo_documento': self.tipo_documento,
            'documento': self.documento,
            'razon_social_o_nombre': self.razon_social_o_nombre,
            'contacto': self.contacto,
            'telefono': self.telefono,
            'correo': self.correo,
            'departamento': self.departamento,
            'municipio': self.municipio,
            'direccion': self.direccion,
            'estado': self.estado
        }


class Compra(db.Model):
    __tablename__ = 'compra'
    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=False)
    total = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    estado_compra = db.Column(db.Boolean, default=True)
    detalles = db.relationship('DetalleCompra', backref='compra', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'proveedor_id': self.proveedor_id,
            'total': self.total,
            'fecha': self.fecha.isoformat(),
            'estado_compra': self.estado_compra
        }


class DetalleCompra(db.Model):
    __tablename__ = 'detalle_compra'
    id = db.Column(db.Integer, primary_key=True)
    compra_id = db.Column(db.Integer, db.ForeignKey('compra.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    precio_unidad = db.Column(db.Float, nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'compra_id': self.compra_id,
            'producto_id': self.producto_id,
            'precio_unidad': self.precio_unidad,
            'cantidad': self.cantidad,
            'subtotal': self.subtotal
        }


# ============================================================
# TABLAS DE SERVICIOS Y CITAS
# ============================================================

class Servicio(db.Model):
    __tablename__ = 'servicio'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(65), nullable=False)
    duracion_min = db.Column(db.Integer, nullable=False)
    precio = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.String(500))
    estado = db.Column(db.Boolean, default=True)
    citas = db.relationship('Cita', backref='servicio', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'duracion_min': self.duracion_min,
            'precio': self.precio,
            'descripcion': self.descripcion,
            'estado': self.estado
        }


# ============================================================
# TABLAS DE EMPLEADOS Y CLIENTES
# ============================================================

class Empleado(db.Model):
    __tablename__ = 'empleado'
    id = db.Column(db.Integer, primary_key=True)
    tipo_documento = db.Column(db.String(20))
    numero_documento = db.Column(db.String(20), nullable=False, unique=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=True)   # Permitir nulos temporalmente
    telefono = db.Column(db.String(15))
    direccion = db.Column(db.String(150))
    fecha_ingreso = db.Column(db.Date, nullable=False)
    cargo = db.Column(db.String(50))
    correo = db.Column(db.String(100), unique=True)
    estado = db.Column(db.Boolean, default=True)
    
    citas = db.relationship('Cita', backref='empleado', lazy=True)
    horarios = db.relationship('Horario', backref='empleado', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'apellido': self.apellido,  # ← AGREGAR
            'nombre_completo': f"{self.nombre} {self.apellido}".strip(),  # ← UTILIDAD
            'tipo_documento': self.tipo_documento,
            'numero_documento': self.numero_documento,
            'telefono': self.telefono,
            'direccion': self.direccion,
            'correo': self.correo,
            'fecha_ingreso': self.fecha_ingreso.isoformat() if self.fecha_ingreso else None,
            'cargo': self.cargo,
            'estado': self.estado,
        }


class Cliente(db.Model):
    __tablename__ = 'cliente'
    id = db.Column(db.Integer, primary_key=True)
    tipo_documento = db.Column(db.String(4))
    numero_documento = db.Column(db.String(20), nullable=False, unique=True)
    nombre = db.Column(db.String(25), nullable=False)
    apellido = db.Column(db.String(20), nullable=False)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    genero = db.Column(db.String(10))
    telefono = db.Column(db.String(20))
    correo = db.Column(db.String(30), unique=True)
    municipio = db.Column(db.String(50))
    direccion = db.Column(db.String(100))
    departamento = db.Column(db.String(50))
    barrio = db.Column(db.String(50))
    codigo_postal = db.Column(db.String(10))
    ocupacion = db.Column(db.String(20))
    telefono_emergencia = db.Column(db.String(20))
    estado = db.Column(db.Boolean, default=True)
    
    citas = db.relationship('Cita', backref='cliente', lazy=True)
    historiales = db.relationship('HistorialFormula', backref='cliente', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'tipo_documento': self.tipo_documento,
            'numero_documento': self.numero_documento,
            'nombre': self.nombre,
            'apellido': self.apellido,
            'fecha_nacimiento': self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None,
            'genero': self.genero,
            'telefono': self.telefono,
            'correo': self.correo,
            'departamento': self.departamento,
            'municipio': self.municipio,
            'barrio': self.barrio,
            'direccion': self.direccion,
            'codigo_postal': self.codigo_postal,
            'ocupacion': self.ocupacion,
            'telefono_emergencia': self.telefono_emergencia,
            'estado': self.estado
        }


# ============================================================
# TABLAS DE CITAS
# ============================================================

class Cita(db.Model):
    __tablename__ = 'cita'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    servicio_id = db.Column(db.Integer, db.ForeignKey('servicio.id'), nullable=False)
    empleado_id = db.Column(db.Integer, db.ForeignKey('empleado.id'), nullable=False)
    metodo_pago = db.Column(db.String(15))
    hora = db.Column(db.Time, nullable=False)
    duracion = db.Column(db.Integer)
    fecha = db.Column(db.Date, nullable=False)
    estado_cita_id = db.Column(db.Integer, db.ForeignKey('estado_cita.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'cliente_id': self.cliente_id,
            'servicio_id': self.servicio_id,
            'empleado_id': self.empleado_id,
            'metodo_pago': self.metodo_pago,
            'hora': self.hora.isoformat() if self.hora else None,
            'duracion': self.duracion,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'estado_cita_id': self.estado_cita_id,
            'estado_nombre': self.estado_cita.nombre if self.estado_cita else None,
            'cliente_nombre': f"{self.cliente.nombre} {self.cliente.apellido}" if self.cliente else None,
            'servicio_nombre': self.servicio.nombre if self.servicio else None,
            'servicio_precio': self.servicio.precio if self.servicio else None,
            'empleado_nombre': self.empleado.nombre if self.empleado else None
        }


class EstadoCita(db.Model):
    __tablename__ = 'estado_cita'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(23), nullable=False)
    citas = db.relationship('Cita', backref='estado_cita', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre
        }


# ============================================================
# TABLAS DE VENTAS
# ============================================================

class Venta(db.Model):
    __tablename__ = 'venta'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=True, unique=True)
    cita_id = db.Column(db.Integer, db.ForeignKey('cita.id'), nullable=True, unique=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    fecha_pedido = db.Column(db.DateTime)
    fecha_venta = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float, nullable=False)
    metodo_pago = db.Column(db.String(20))
    metodo_entrega = db.Column(db.String(20))
    direccion_entrega = db.Column(db.String(255))
    transferencia_comprobante = db.Column(db.String(255))
    estado_id = db.Column(db.Integer, db.ForeignKey('estado_venta.id'), nullable=False)
    estado_venta = db.relationship('EstadoVenta', backref='ventas')
    cliente = db.relationship('Cliente', backref='ventas')
    pedido = db.relationship('Pedido', backref='venta', uselist=False)
    cita = db.relationship('Cita', backref='venta', uselist=False)
    detalles = db.relationship('DetalleVenta', backref='venta', lazy=True, cascade='all, delete-orphan')
    abonos = db.relationship('Abono', foreign_keys='Abono.venta_id', backref='venta', lazy=True)

    @property
    def saldo_pendiente(self):
        return self.total - sum(abono.monto for abono in self.abonos)

    def to_dict(self):
        return {
            'id': self.id,
            'pedido_id': self.pedido_id,
            'cita_id': self.cita_id,
            'cliente_id': self.cliente_id,
            'fecha_pedido': self.fecha_pedido.isoformat() if self.fecha_pedido else None,
            'fecha_venta': self.fecha_venta.isoformat() if self.fecha_venta else None,
            'total': self.total,
            'metodo_pago': self.metodo_pago,
            'metodo_entrega': self.metodo_entrega,
            'direccion_entrega': self.direccion_entrega,
            'transferencia_comprobante': self.transferencia_comprobante,
            'estado_id': self.estado_id,
            'estado_nombre': self.estado_venta.nombre if self.estado_venta else None,
            'saldo_pendiente': self.saldo_pendiente,
            'cliente_nombre': self.cliente.nombre if self.cliente else None,
            'cita_fecha': self.cita.fecha.isoformat() if self.cita else None,
            'cita_servicio': self.cita.servicio.nombre if self.cita else None,
            'detalles': [item.to_dict() for item in self.detalles] if self.detalles else [],
            'abonos': [abono.to_dict() for abono in self.abonos] if self.abonos else []
        }


class DetalleVenta(db.Model):
    __tablename__ = 'detalle_venta'
    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey('venta.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=True)
    servicio_id = db.Column(db.Integer, db.ForeignKey('servicio.id'), nullable=True)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)
    descuento = db.Column(db.Float, default=0.0)
    subtotal = db.Column(db.Float, nullable=False)
    producto = db.relationship('Producto', backref='detalle_ventas')
    servicio = db.relationship('Servicio', backref='detalle_ventas')

    def to_dict(self):
        return {
            'id': self.id,
            'venta_id': self.venta_id,
            'producto_id': self.producto_id,
            'producto_nombre': self.producto.nombre if self.producto else None,
            'servicio_id': self.servicio_id,
            'servicio_nombre': self.servicio.nombre if self.servicio else None,
            'cantidad': self.cantidad,
            'precio_unitario': self.precio_unitario,
            'descuento': self.descuento,
            'subtotal': self.subtotal
        }


class EstadoVenta(db.Model):
    __tablename__ = 'estado_venta'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(20), nullable=False, unique=True)

    def to_dict(self):
        return {'id': self.id, 'nombre': self.nombre}


# ============================================================
# TABLAS ADICIONALES
# ============================================================

class Horario(db.Model):
    __tablename__ = 'horario'
    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('empleado.id'), nullable=False)
    dia = db.Column(db.Integer, nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_final = db.Column(db.Time, nullable=False)
    activo = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'empleado_id': self.empleado_id,
            'dia': self.dia,
            'hora_inicio': self.hora_inicio.isoformat(),
            'hora_final': self.hora_final.isoformat(),
            'activo': self.activo
        }


class Novedad(db.Model):
    __tablename__ = 'novedad'
    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('empleado.id'), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.Time, nullable=True)
    hora_fin = db.Column(db.Time, nullable=True)
    tipo = db.Column(db.String(50), nullable=False)
    motivo = db.Column(db.String(255), nullable=True)
    activo = db.Column(db.Boolean, default=True)
    empleado = db.relationship('Empleado', backref='novedades')

    def to_dict(self):
        return {
            'id': self.id,
            'empleado_id': self.empleado_id,
            'fecha_inicio': self.fecha_inicio.isoformat(),
            'fecha_fin': self.fecha_fin.isoformat(),
            'hora_inicio': self.hora_inicio.strftime('%H:%M') if self.hora_inicio else None,
            'hora_fin': self.hora_fin.strftime('%H:%M') if self.hora_fin else None,
            'tipo': self.tipo,
            'motivo': self.motivo,
            'activo': self.activo
        }


class HistorialFormula(db.Model):
    __tablename__ = 'historial_formula'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    descripcion = db.Column(db.String(500))
    od_esfera = db.Column(db.String(10))
    od_cilindro = db.Column(db.String(10))
    od_eje = db.Column(db.String(10))
    oi_esfera = db.Column(db.String(10))
    oi_cilindro = db.Column(db.String(10))
    oi_eje = db.Column(db.String(10))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'cliente_id': self.cliente_id,
            'descripcion': self.descripcion,
            'fecha': self.fecha.isoformat(),
            'od_esfera': self.od_esfera,
            'od_cilindro': self.od_cilindro,
            'od_eje': self.od_eje,
            'oi_esfera': self.oi_esfera,
            'oi_cilindro': self.oi_cilindro,
            'oi_eje': self.oi_eje,
        }


class CampanaSalud(db.Model):
    __tablename__ = 'campana_salud'
    
    id = db.Column(db.Integer, primary_key=True)
    empleado_id = db.Column(db.Integer, db.ForeignKey('empleado.id'), nullable=False)
    empresa = db.Column(db.String(60), nullable=False)
    nit_empresa = db.Column(db.String(30), unique=True, nullable=False)
    contacto = db.Column(db.String(15))
    fecha = db.Column(db.DateTime, nullable=False)
    hora = db.Column(db.Time, nullable=False)
    direccion = db.Column(db.String(30))
    observaciones = db.Column(db.String(500))
    descripcion = db.Column(db.String(500))
    estado_cita_id = db.Column(db.Integer, db.ForeignKey('estado_cita.id'), nullable=False, default=2)
    
    empleado = db.relationship('Empleado', backref='campanas_salud', lazy=True)
    estado_cita = db.relationship('EstadoCita', backref='campanas_salud', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'empleado_id': self.empleado_id,
            'empleado_nombre': self.empleado.nombre if self.empleado else None,
            'empresa': self.empresa,
            'nit_empresa': self.nit_empresa,
            'contacto': self.contacto,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'hora': self.hora.isoformat() if self.hora else None,
            'direccion': self.direccion,
            'observaciones': self.observaciones,
            'descripcion': self.descripcion,
            'estado_cita_id': self.estado_cita_id,
            'estado_nombre': self.estado_cita.nombre if self.estado_cita else None
        }


class Multimedia(db.Model):
    __tablename__ = 'multimedia'
    
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    categoria_id = db.Column(db.Integer, nullable=True)
    pedido_id = db.Column(db.Integer, nullable=True)
    tipo = db.Column(db.String(20), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'categoria_id': self.categoria_id,
            'pedido_id': self.pedido_id,
            'tipo': self.tipo
        }