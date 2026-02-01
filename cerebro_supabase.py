import os
from supabase import create_client, Client

# --- CONFIGURACIÓN SUPABASE ---
# Estas variables las pondremos en Render en el Paso 4
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

def get_supabase():
    if not URL or not KEY:
        print("❌ Error: Faltan las credenciales de SUPABASE en las variables de entorno.")
        return None
    try:
        client: Client = create_client(URL, KEY)
        return client
    except Exception as e:
        print(f"❌ Error conectando con Supabase: {e}")
        return None

def guardar_gasto(datos_gasto):
    """
    Guarda el gasto en la tabla 'gastos' de Supabase.
    """
    supabase = get_supabase()
    if not supabase:
        return False

    try:
        # Preparamos los datos para que coincidan con las columnas de tu base de datos
        # Nota: Asegúrate que tu tabla en Supabase se llame 'gastos' (o cambia el nombre abajo)
        payload = {
            "fecha": datos_gasto['fecha'],
            "item": datos_gasto['item'],
            "monto": datos_gasto['monto'],       # Asegúrate que en Supabase sea tipo numero
            "categoria": datos_gasto['categoria'],
            "cuenta": datos_gasto['cuenta'],
            "detalle": datos_gasto.get('detalle', ''),
            "tipo": datos_gasto['tipo']
        }

        # Ejecutamos la inserción
        response = supabase.table('gastos').insert(payload).execute()
        
        # Verificamos si hubo respuesta exitosa
        # Supabase devuelve los datos insertados en response.data
        if response.data:
            print(f"✅ Guardado en Supabase: {payload['item']}")
            return True
        else:
            print("⚠️ No se recibió confirmación de Supabase.")
            return False

    except Exception as e:
        print(f"❌ Error guardando en Supabase: {e}")
        return False