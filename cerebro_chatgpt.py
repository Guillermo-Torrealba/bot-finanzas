import os
import json
from openai import OpenAI
from datetime import datetime, timedelta

# Configuración de la API Key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- 1. TRANSCRIPCIÓN DE AUDIO (WHISPER) ---
def transcribir_audio(ruta_audio):
    print(f"🎤 Iniciando transcripción de: {ruta_audio}")
    try:
        with open(ruta_audio, "rb") as archivo:
            transcripcion = client.audio.transcriptions.create(
                model="whisper-1", 
                file=archivo,
                language="es"
            )
            print(f"📝 Texto detectado: {transcripcion.text}")
            return transcripcion.text
    except Exception as e:
        print(f"❌ Error al transcribir: {e}")
        return ""

# --- 2. EL ROUTER (Detecta si es Gasto o Pregunta) ---
def decidir_intencion(texto):
    """
    Decide si el texto es un 'GASTO' (anotar) o una 'CONSULTA' (preguntar).
    """
    prompt = f"""
    Analiza la siguiente frase: "{texto}"
    Responde SOLO una palabra:
    - "GASTO": si el usuario está reportando un pago, compra o ingreso.
    - "CONSULTA": si el usuario está preguntando totales, resumenes, cuánto gastó, etc.
    - "OTRO": si es irrelevante.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip().upper()
    except:
        return "GASTO"

# --- 3. ANALISTA DE DATOS (Responde preguntas) ---
def analizar_consultas_ia(pregunta, dataframe_gastos):
    """
    Recibe la pregunta del usuario y la tabla de gastos (DataFrame) para responder.
    """
    if dataframe_gastos is None or dataframe_gastos.empty:
        return "No tengo datos registrados aún para analizar."

    # Convertimos las ultimas 50 filas a CSV para dar contexto
    csv_data = dataframe_gastos.tail(50).to_csv(index=False)
    hoy = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
    Eres un asesor financiero personal (CFO). Hoy es {hoy}.
    Tienes acceso a estos gastos recientes del usuario:
    
    {csv_data}
    
    El usuario pregunta: "{pregunta}"
    
    Instrucciones:
    1. Responde basándote SOLO en los datos.
    2. Si sumas montos, hazlo con cuidado.
    3. Sé breve y directo.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Me mareé con los números 😵. Error: {e}"

# --- 4. INTERPRETAR GASTO (TU VERSIÓN PERSONALIZADA) ---
def interpretar_gasto(texto_usuario):
    # Cálculo de fechas exactas
    hoy = datetime.now()
    fecha_hoy = hoy.strftime("%Y-%m-%d")
    fecha_ayer = (hoy - timedelta(days=1)).strftime("%Y-%m-%d")
    fecha_antier = (hoy - timedelta(days=2)).strftime("%Y-%m-%d")
    dia_semana = hoy.strftime("%A")

    # --- TU DICCIONARIO PERSONAL ---
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
    
    prompt = f"""
    HOY es {dia_semana}, {fecha_hoy}.
    AYER fue: {fecha_ayer}
    ANTEAYER fue: {fecha_antier}

    Analiza: "{texto_usuario}"
    
    TAREAS:
    1. Tipo: "Gasto" o "Ingreso".
    2. MONTO (Reglas de Oro):
       - "lucas", "mil", "k" -> MULTIPLICA por 1000. (Ej: "3 lucas" -> 3000).
       - Número solo -> ÚSALO EXACTO.
    3. Cuenta: ['Débito BICE', 'Crédito BICE', 'Mercado Pago', 'Efectivo']. (Si no dice, null).
    
    4. FECHA OBLIGATORIA:
       - "ayer" -> "{fecha_ayer}"
       - "antier" -> "{fecha_antier}"
       - Default -> "{fecha_hoy}"
    
    5. CATEGORÍA:
       {diccionario_personal}
       - Si no está, inventa una lógica (Ej: Farmacia, Comida).

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
        return json.loads(texto)

    except Exception as e:
        print(f"❌ Error ChatGPT: {e}")
        return {"gastos": [{"item": "Error", "monto": 0}]}

# --- 5. NORMALIZAR CUENTA (Con tus Bancos) ---
def normalizar_cuenta(texto_corto):
    prompt = f"""
    Normaliza este medio de pago: "{texto_corto}"
    Opciones: ['Débito BICE', 'Crédito BICE', 'Mercado Pago', 'Efectivo']
    Responde solo el nombre oficial exacto de la lista.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except:
        return "Débito BICE"
