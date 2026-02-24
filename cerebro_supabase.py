import os
from supabase import create_client, Client

# --- CONFIGURACIÓN SUPABASE ---
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

# --- CLIENTE GLOBAL ---
# Creamos la variable 'supabase' aquí afuera para que app.py la pueda importar
supabase: Client = None

if URL and KEY:
    try:
        supabase = create_client(URL, KEY)
    except Exception as e:
        print(f"❌ Error inicializando Supabase: {e}")
else:
    print("❌ Error: Faltan las variables SUPABASE_URL o SUPABASE_KEY")

def get_supabase():
    """Retorna el cliente global ya inicializado"""
    return supabase

def guardar_gasto(datos_gasto):
    """
    Guarda el gasto en la tabla 'gastos' de Supabase.
    Ahora incluye el 'user_id' si viene en los datos.
    """
    if not supabase:
        print("❌ No hay conexión con Supabase.")
        return False

    try:
        # Preparamos los datos
        payload = {
            "fecha": datos_gasto['fecha'],
            "item": datos_gasto['item'],
            "monto": datos_gasto['monto'],
            "categoria": datos_gasto['categoria'],
            "cuenta": datos_gasto['cuenta'],
            "metodo_pago": datos_gasto.get('metodo_pago'),
            "detalle": datos_gasto.get('detalle', ''),
            "tipo": datos_gasto['tipo'],
            
            # --- NUEVO: Agregamos el ID del usuario ---
            "user_id": datos_gasto.get('user_id') 
        }

        # Ejecutamos la inserción
        response = supabase.table('gastos').insert(payload).execute()
        
        # Verificamos respuesta
        if response.data:
            print(f"✅ Guardado en Supabase: {payload['item']}")
            return True
        else:
            # A veces Supabase devuelve vacío aunque guarde bien, pero asumimos éxito si no hay error
            print(f"✅ Guardado (sin data de retorno): {payload['item']}")
            return True

    except Exception as e:
        print(f"❌ Error guardando en Supabase: {e}")
        return False

def obtener_ultimos_gastos(user_id):
    """Descarga los últimos 50 movimientos del usuario para análisis"""
    if not supabase: return []
    
    try:
        # Traemos los últimos 50 gastos, ordenados por fecha
        response = supabase.table("gastos")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("fecha", desc=True)\
            .limit(50)\
            .execute()
        return response.data
    except Exception as e:
        print(f"❌ Error leyendo gastos: {e}")
        return []