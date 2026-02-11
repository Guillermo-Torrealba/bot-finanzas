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
    REGLAS DE CATEGORIZACIÓN PARA GASTOS:
    - Si dice "promo", "piscola", "copete", "disco", "entrada", "tabaco", "papelillos", "filtros" -> Categoría: "Carrete"
    - Si dice "uber", "didi", "cabify", "metro", "bip", "scooter", "pasaje bus" -> Categoría: "Transporte"
    - Si dice "jumbo", "lider", "mercado" -> Categoría: "Supermercado"
    - Si dice "padel", "futbol", "cancha" -> Categoría: "Deporte"
    - Si dice "icloud" -> Categoría: "Suscripciones"
    - Si dice "regalo" -> Categoría: "Regalos"
    - Si dice "peluqueria" -> Categoría: "Peluquería"

    REGLAS DE CATEGORIZACIÓN PARA INGRESOS:
    - Si dice "sueldo", "pega", "trabajo", "nómina", "salario" -> Categoría: "Sueldo"
    - Si dice "freelance", "proyecto", "cliente", "honorarios" -> Categoría: "Freelance"
    - Si dice "transferencia", "me mandaron", "me depositaron", "me pagaron" -> Categoría: "Transferencia Recibida"
    - Si dice "reembolso", "devolución", "me devolvieron" -> Categoría: "Reembolso"
    - Si dice "arriendo", "alquiler" -> Categoría: "Arriendo"
    - Si dice "vendí", "venta" -> Categoría: "Venta"
    - Si dice "inversión", "dividendo", "intereses", "rendimiento" -> Categoría: "Inversiones"
    - Si dice "mesada" -> Categoría: "Mesada"
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
    3. Cuenta: ['Banco BICE', 'Mercado Pago']. (Si no dice, null).
       - "Banco BICE" = cualquier referencia a BICE, banco, tarjeta BICE, etc.
       - "Mercado Pago" = cualquier referencia a mercado pago, MP, etc.
    3b. Método de pago (metodo_pago): ['Débito', 'Crédito']. (Si no dice, null).
       - Si dice "débito", "debito", "tarjeta de débito" -> "Débito"
       - Si dice "crédito", "credito", "tarjeta de crédito" -> "Crédito"
    
    4. FECHA OBLIGATORIA:
       - Si dice "ayer", DEBES poner "{fecha_ayer}".
       - Si dice "antier" o "antes de ayer", pon "{fecha_antier}".
       - Si NO dice fecha, pon "{fecha_hoy}".
       - Formato: YYYY-MM-DD.
5. CATEGORÍA:
        - Primero revisa este diccionario de reglas personales: {diccionario_personal}
        - Si el item está ahí, usa esa categoría exacta.
        - Si NO está en el diccionario, clasifica según el TIPO:

          ** Si es GASTO, usa OBLIGATORIAMENTE una de estas categorías:
          ['Comida', 'Transporte', 'Regalos', 'Suscripciones', 'Carrete', 'Panoramas', 'Ropa', 'Bencina', 'Salud', 'Deportes', 'Peluquería', 'Supermercado', 'Varios']
          REGLAS para gastos:
            * "Carrete": Alcohol, fiestas, salidas nocturnas, bares.
            * "Panoramas": Cine, conciertos, salidas diurnas, entretenimiento.
            * "Supermercado": Compras de mercadería para la casa.
            * "Comida": Restaurantes, delivery, comida rápida.
            * Si no encaja en ninguna, usa 'Varios'.

          ** Si es INGRESO, usa OBLIGATORIAMENTE una de estas categorías:
          ['Sueldo', 'Freelance', 'Transferencia Recibida', 'Inversiones', 'Reembolso', 'Arriendo', 'Venta', 'Otros Ingresos']
          REGLAS para ingresos:
            * "Sueldo": Salario mensual, quincena, pago de trabajo fijo.
            * "Freelance": Pagos por trabajos independientes, proyectos, honorarios.
            * "Transferencia Recibida": Dinero que te mandan, depósitos de terceros.
            * "Inversiones": Dividendos, rendimientos, intereses.
            * "Reembolso": Devoluciones de dinero.
            * "Arriendo": Ingresos por arriendo de propiedades.
            * "Venta": Dinero recibido por vender algo.
            * Si no encaja en ninguna, usa 'Otros Ingresos'.
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
                "metodo_pago": null,
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
    Opciones de cuenta: ['Banco BICE', 'Mercado Pago']
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
        return None