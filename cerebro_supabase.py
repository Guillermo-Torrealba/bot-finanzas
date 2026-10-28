import os
from datetime import datetime # <--- AGREGADO IMPORTANTE
from supabase import create_client, Client

# --- CONFIGURACIÓN SUPABASE ---
URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_KEY")

# --- CLIENTE GLOBAL ---
supabase: Client = None

if URL and KEY:
    try:
        supabase = create_client(URL, KEY)
    except Exception as e:
        print(f"❌ Error inicializando Supabase ({type(e).__name__}).")
else:
    print("❌ Error: Faltan las variables SUPABASE_URL o SUPABASE_KEY")

def get_supabase():
    """Retorna el cliente global ya inicializado"""
    return supabase

def guardar_gasto(datos_gasto):
    """
    Guarda el gasto en la tabla 'gastos' de Supabase.
    """
    if not supabase:
        print("❌ No hay conexión con Supabase.")
        return False
    user_id = datos_gasto.get("user_id")
    if not user_id:
        print("❌ Movimiento rechazado: falta una cuenta autenticada.")
        return False

    try:
        payload = {
            "fecha": datos_gasto['fecha'],
            "item": datos_gasto['item'],
            "monto": datos_gasto['monto'],
            "categoria": datos_gasto['categoria'],
            "cuenta": datos_gasto['cuenta'],
            "metodo_pago": datos_gasto.get('metodo_pago'),
            "detalle": datos_gasto.get('detalle', ''),
            "tipo": datos_gasto['tipo'],
            "user_id": user_id
        }

        response = supabase.table('gastos').insert(payload).execute()
        
        if response.data:
            print("✅ Movimiento guardado en Supabase.")
            return True
        else:
            print("✅ Movimiento guardado en Supabase.")
            return True

    except Exception as e:
        print(f"❌ Error guardando en Supabase ({type(e).__name__}).")
        return False

def obtener_ultimos_gastos(user_id):
    """
    Descarga los gastos desde el PRIMER DÍA del mes actual.
    Esto arregla el error de cálculo en los resúmenes mensuales.
    """
    if not supabase or not user_id:
        return []
    
    try:
        # 1. Calculamos el día 1 del mes actual (Ej: 2026-02-01)
        hoy = datetime.now()
        primer_dia_mes = hoy.replace(day=1).strftime('%Y-%m-%d')

        # 2. Traemos TODO desde esa fecha (sin límite de 50)
        response = supabase.table("gastos")\
            .select("*")\
            .eq("user_id", user_id)\
            .gte("fecha", primer_dia_mes)\
            .order("fecha", desc=True)\
            .execute()
            
        print("📅 Consulta de movimientos completada.")
        return response.data
    except Exception as e:
        print(f"❌ Error leyendo gastos ({type(e).__name__}).")
        return []
