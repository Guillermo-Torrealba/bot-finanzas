from openai import OpenAI
import json
from datetime import datetime, timedelta
import os

# --- PON TU CLAVE ---
CLAVE_OPENAI = os.getenv("OPENAI_API_KEY") 

client = OpenAI(api_key=CLAVE_OPENAI)

def interpretar_gasto(texto_usuario):
    # 1. Calculamos las fechas exactas con Python
    hoy = datetime.now()
    fecha_hoy = hoy.strftime("%Y-%m-%d")
    fecha_ayer = (hoy - timedelta(days=1)).strftime("%Y-%m-%d")
    fecha_antier = (hoy - timedelta(days=2)).strftime("%Y-%m-%d")
    dia_semana = hoy.strftime("%A")

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

    5. Item, Categoría y Detalle.

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