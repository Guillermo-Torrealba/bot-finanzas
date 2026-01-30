from openai import OpenAI
import json
from datetime import datetime, timedelta
import os

# --- PON TU CLAVE ---
CLAVE_OPENAI = os.getenv("OPENAI_API_KEY") 

client = OpenAI(api_key=CLAVE_OPENAI)

# --- NUEVA FUNCIÓN: TRANSCRIPCIÓN DE AUDIO (WHISPER) ---
def transcribir_audio(ruta_audio):
    try:
        with open(ruta_audio, "rb") as archivo:
            transcripcion = client.audio.transcriptions.create(
                model="whisper-1", 
                file=archivo
            )
        return transcripcion.text
    except Exception as e:
        print(f"❌ Error al transcribir: {e}")
        return ""

def interpretar_gasto(texto_usuario):
    # 1. Calculamos las fechas exactas con Python
    hoy = datetime.now()
    fecha_hoy = hoy.strftime("%Y-%m-%d")
    fecha_ayer = (hoy - timedelta(days=1)).strftime("%Y-%m-%d")
    fecha_antier = (hoy - timedelta(days=2)).strftime("%Y-%m-%d")
    dia_semana = hoy.strftime("%A")

    # --- TU DICCIONARIO PERSONAL ---
    # Agrega aquí tus reglas. La IA buscará esto primero.
    diccionario_personal = """
    REGLAS DE CATEGORIZACIÓN:
    - Si dice "promo", "piscola", "copete", "disco", "entrada", "tabaco", "papelillos", "filtros" -> Categoría: "Carrete"
    - Si dice "uber", "didi", "cabify", "metro", "bip", "scooter", "pasaje bus" -> Categoría: "Transporte"
    - Si dice "jumbo", "lider", "mercado" -> Categoría: "Supermercado"
    - Si dice "padel", "futbol", "cancha" -> Categoría: "Deporte"
    - Si dice "icloud" -> Categoría: "Suscripción"
    - Si dice "pasaje", "pasaje avion" -> Categoría: "Pasaje"
    - Si dice "regalo" -> Categoría: "Regalo"
    - Si dice "peluqueria" -> Categoría: "Peluqueria"
    """
    
    # 2. Prompt con instrucciones de fecha claras
    prompt = f"""
    HOY es {dia_semana}, {fecha_hoy}.
    AYER fue: {fecha_ayer}
    ANTEAYER fue: {fecha_antier}

    Analiza: "{texto_usuario}"
    
    TAREAS:
    1. Tipo: "Gasto" o "Ingreso".
    2. MONTO (Reglas de Oro):
       - Si el usuario dice "lucas", "mil" o "k" (ej: "3 lucas", "5k"), MULTIPLICA el número por 1000.
         (Ejemplo: "3 lucas" -> 3000).
       - Si el usuario pone un número solo (ej: "3500"), úsalo EXACTO. NO multipliques.
    3. Cuenta: ['Débito BICE', 'Crédito BICE', 'Mercado Pago', 'Efectivo']. (Si no dice, null).
    
    4. FECHA OBLIGATORIA:
       - Si dice "ayer", DEBES poner "{fecha_ayer}".
       - Si dice "antier" o "antes de ayer", pon "{fecha_antier}".
       - Si NO dice fecha, pon "{fecha_hoy}".
       - Formato: YYYY-MM-DD.
    5. CATEGORÍA (Usa tu inteligencia + este diccionario):
       {diccionario_personal}
       - Si el item NO está en las reglas anteriores, inventa una categoría lógica (ej: "Comida", "Farmacia").
    6. Item: Extrae el producto o servicio.
    7. Detalle: Información extra (ej: "con amigos").

    Responde JSON:
    {{
        "gastos": [
            {{
                "tipo": "Gasto",
                "monto": 0,
                "item": "str",
                "categoria": "str",
                "cuenta": null,
                "fecha": "YYYY-MM-DD",
                "detalle": "str"
            }}
        ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        texto = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
        datos = json.loads(texto)
        
        # --- DIAGNÓSTICO: ESTO SALDRÁ EN TU TERMINAL ---
        print(f"🧠 CEREBRO PENSÓ: {datos}") 
        # -----------------------------------------------
        
        return datos

    except Exception as e:
        print(f"❌ Error ChatGPT: {e}")
        return {"gastos": []}

def normalizar_cuenta(texto_corto):
    prompt = f"""
    Normaliza este medio de pago: "{texto_corto}"
    Opciones: ['Débito BICE', 'Crédito BICE', 'Mercado Pago', 'Efectivo', 'Santander']
    Responde solo el nombre oficial.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except:
        return "Efectivo"
        return "Efectivo"
    elif "mercado" in texto:
        return "Mercado Pago"
    else:
        return "Banco Falabella" # Valor por defecto si no se sabe


