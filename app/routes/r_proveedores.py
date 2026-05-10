from flask import jsonify, request
from app.database import db
from app.Models.models import Proveedor, Compra
from app.routes import main_bp
from app.auth.decorators import permiso_requerido
import re

# Regex para validar email
EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
# Regex para validar teléfono (solo números, 7-15 dígitos)
PHONE_REGEX = re.compile(r'^\d{7,15}$')


# ============================================================
# MÓDULO: PROVEEDORES
# ============================================================

@main_bp.route('/proveedores', methods=['GET'])
@permiso_requerido("proveedores")
def get_proveedores():
    try:
        proveedores = Proveedor.query.order_by(Proveedor.razon_social_o_nombre.asc()).all()
        return jsonify([proveedor.to_dict() for proveedor in proveedores])
    except Exception as e:
        return jsonify({"error": f"Error al obtener proveedores: {str(e)}"}), 500


@main_bp.route('/proveedores', methods=['POST'])
@permiso_requerido("proveedores")
def create_proveedor():
    try:
        data = request.get_json()
        
        # 1. Validar campos obligatorios
        razon_social = data.get('razon_social_o_nombre', '').strip()
        documento = data.get('documento', '').strip()
        
        if not razon_social:
            return jsonify({"error": "La razón social o nombre del proveedor es requerido"}), 400
        if not documento:
            return jsonify({"error": "El documento (NIT/Cédula) del proveedor es requerido"}), 400
        
        # 2. Validar tipo de proveedor
        tipo_proveedor = data.get('tipo_proveedor')
        if tipo_proveedor and tipo_proveedor not in ['Persona Natural', 'Persona Jurídica']:
            return jsonify({"error": "Tipo de proveedor inválido. Opciones: 'Persona Natural' o 'Persona Jurídica'"}), 400
        
        # 3. Validar tipo de documento
        tipo_documento = data.get('tipo_documento', '').strip()
        if tipo_documento and tipo_documento not in ['CC', 'NIT', 'CE', 'Pasaporte']:
            return jsonify({"error": "Tipo de documento inválido. Opciones: CC, NIT, CE, Pasaporte"}), 400
        
        # 4. Validar documento único
        if Proveedor.query.filter_by(documento=documento).first():
            return jsonify({"error": f"Ya existe un proveedor con el documento {documento}"}), 400
        
        # 5. Validar email (si se proporciona)
        correo = data.get('correo', '').strip()
        if correo and not EMAIL_REGEX.match(correo):
            return jsonify({"error": "Formato de correo electrónico inválido"}), 400
        
        # 6. Validar teléfono (si se proporciona)
        telefono = data.get('telefono', '').strip()
        if telefono and not PHONE_REGEX.match(telefono):
            return jsonify({"error": "El teléfono debe contener solo números (7-15 dígitos)"}), 400
        
        # 7. Validar contacto (si se proporciona)
        contacto = data.get('contacto', '').strip()
        if contacto and len(contacto) > 50:
            return jsonify({"error": "El nombre de contacto no puede tener más de 50 caracteres"}), 400
        
        # 8. Validar longitud de campos
        if len(razon_social) > 100:
            return jsonify({"error": "La razón social no puede tener más de 100 caracteres"}), 400
        if len(documento) > 20:
            return jsonify({"error": "El documento no puede tener más de 20 caracteres"}), 400
        
        proveedor = Proveedor(
            tipo_proveedor=tipo_proveedor,
            tipo_documento=tipo_documento if tipo_documento else None,
            documento=documento,
            razon_social_o_nombre=razon_social,
            contacto=contacto if contacto else None,
            telefono=telefono if telefono else None,
            correo=correo if correo else None,
            departamento=data.get('departamento', '').strip() or None,
            municipio=data.get('municipio', '').strip() or None,
            direccion=data.get('direccion', '').strip() or None,
            estado=data.get('estado', True)
        )
        
        db.session.add(proveedor)
        db.session.commit()
        return jsonify({"message": "Proveedor creado", "proveedor": proveedor.to_dict()}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al crear proveedor: {str(e)}"}), 500


@main_bp.route('/proveedores/<int:id>', methods=['PUT'])
@permiso_requerido("proveedores")
def update_proveedor(id):
    try:
        proveedor = Proveedor.query.get(id)
        if not proveedor:
            return jsonify({"error": "Proveedor no encontrado"}), 404
        
        data = request.get_json()
        
        # Validar tipo de proveedor
        if 'tipo_proveedor' in data:
            tipo = data['tipo_proveedor']
            if tipo and tipo not in ['Persona Natural', 'Persona Jurídica']:
                return jsonify({"error": "Tipo de proveedor inválido. Opciones: 'Persona Natural' o 'Persona Jurídica'"}), 400
            proveedor.tipo_proveedor = tipo
        
        # Validar tipo de documento
        if 'tipo_documento' in data:
            tipo_doc = data['tipo_documento'].strip() if data['tipo_documento'] else None
            if tipo_doc and tipo_doc not in ['CC', 'NIT', 'CE', 'Pasaporte']:
                return jsonify({"error": "Tipo de documento inválido. Opciones: CC, NIT, CE, Pasaporte"}), 400
            proveedor.tipo_documento = tipo_doc
        
        # Validar documento único (si cambia)
        if 'documento' in data:
            nuevo_documento = data['documento'].strip()
            if not nuevo_documento:
                return jsonify({"error": "El documento no puede estar vacío"}), 400
            
            existente = Proveedor.query.filter(
                Proveedor.documento == nuevo_documento,
                Proveedor.id != id
            ).first()
            if existente:
                return jsonify({"error": f"Ya existe otro proveedor con el documento {nuevo_documento}"}), 400
            proveedor.documento = nuevo_documento
        
        # Validar razón social
        if 'razon_social_o_nombre' in data:
            razon = data['razon_social_o_nombre'].strip()
            if not razon:
                return jsonify({"error": "La razón social no puede estar vacía"}), 400
            if len(razon) > 100:
                return jsonify({"error": "La razón social no puede tener más de 100 caracteres"}), 400
            proveedor.razon_social_o_nombre = razon
        
        # Validar contacto
        if 'contacto' in data:
            contacto = data['contacto'].strip() if data['contacto'] else None
            if contacto and len(contacto) > 50:
                return jsonify({"error": "El nombre de contacto no puede tener más de 50 caracteres"}), 400
            proveedor.contacto = contacto
        
        # Validar email
        if 'correo' in data:
            correo = data['correo'].strip() if data['correo'] else None
            if correo and not EMAIL_REGEX.match(correo):
                return jsonify({"error": "Formato de correo electrónico inválido"}), 400
            proveedor.correo = correo
        
        # Validar teléfono
        if 'telefono' in data:
            telefono = data['telefono'].strip() if data['telefono'] else None
            if telefono and not PHONE_REGEX.match(telefono):
                return jsonify({"error": "El teléfono debe contener solo números (7-15 dígitos)"}), 400
            proveedor.telefono = telefono
        
        # Validar estado: No desactivar si tiene compras asociadas
        if 'estado' in data and not data['estado']:
            compras_asociadas = Compra.query.filter_by(proveedor_id=id).first()
            if compras_asociadas:
                return jsonify({
                    "error": "No se puede desactivar un proveedor que tiene compras asociadas"
                }), 400
            proveedor.estado = data['estado']
        elif 'estado' in data:
            proveedor.estado = data['estado']
        
        # Actualizar campos simples
        if 'departamento' in data:
            proveedor.departamento = data['departamento'].strip() if data['departamento'] else None
        if 'municipio' in data:
            proveedor.municipio = data['municipio'].strip() if data['municipio'] else None
        if 'direccion' in data:
            proveedor.direccion = data['direccion'].strip() if data['direccion'] else None
        
        db.session.commit()
        return jsonify({"message": "Proveedor actualizado", "proveedor": proveedor.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al actualizar proveedor: {str(e)}"}), 500


@main_bp.route('/proveedores/<int:id>', methods=['DELETE'])
@permiso_requerido("proveedores")
def delete_proveedor(id):
    try:
        proveedor = Proveedor.query.get(id)
        if not proveedor:
            return jsonify({"error": "Proveedor no encontrado"}), 404
        
        # 1. Validar que no tenga compras asociadas
        compras_asociadas = Compra.query.filter_by(proveedor_id=id).first()
        if compras_asociadas:
            return jsonify({
                "error": "No se puede eliminar: Este proveedor tiene historial de compras. Desactívelo para ocultarlo."
            }), 400
        
        # 2. Validar que el proveedor esté desactivado
        if proveedor.estado:
            return jsonify({
                "error": "Debes desactivar el proveedor antes de eliminarlo"
            }), 400
        
        db.session.delete(proveedor)
        db.session.commit()
        return jsonify({"message": "Proveedor eliminado correctamente"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error al eliminar proveedor: {str(e)}"}), 500