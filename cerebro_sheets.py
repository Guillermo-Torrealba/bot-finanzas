import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd

def guardar_en_sheets(datos):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # --- LÓGICA HÍBRIDA (PC vs NUBE) ---
    if os.path.exists("credenciales.json"):
        # Estamos en tu PC
        creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
    else:
        # Estamos en la Nube (Render)
        # Leeremos el JSON desde una variable oculta
        json_info = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json_info, scope)
    
    client = gspread.authorize(creds)
    sheet = client.open("Finanzas Personales").sheet1
    
    # ... (El resto de tu lógica de fechas y guardado sigue IGUAL hacia abajo) ...
    # Copia aquí tu lógica de fechas y append_row que ya tenías funcionando
    
    # --- LÓGICA DE FECHA (Pégala aquí igual que antes) ---
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    fecha_ia = datos.get('fecha') 

    if fecha_ia and fecha_ia != fecha_hoy:
        fecha_final = f"{fecha_ia} 12:00"
    else:
        fecha_final = datetime.now().strftime("%Y-%m-%d %H:%M")

    fila = [
        datos.get('tipo', 'Gasto'),
        datos.get('monto', 0),
        datos.get('item', 'Varios'),
        datos.get('categoria', 'General'),
        fecha_final,
        datos.get('cuenta', 'Principal'),
        datos.get('detalle', '')
    ]

    sheet.append_row(fila)
    return True

    sheet.append_row(fila)

    return True

def obtener_gastos_mes_actual():
    """
    Descarga los datos de Google Sheets y los convierte en un DataFrame de Pandas.
    Filtra solo los datos del mes actual para no sobrecargar a la IA.
    """
    try:
        # Descargar todos los registros de la hoja "Gastos"
        registros = sheet.get_all_records()
        
        if not registros:
            return None

        # Convertir a DataFrame (Tabla inteligente)
        df = pd.DataFrame(registros)

        # Limpieza de datos básica
        # Convertir columna 'monto' a números (quitando signos $ y puntos)
        # Ojo: Ajusta esto si tus columnas se llaman diferente en el Excel
        if 'monto' in df.columns:
            df['monto'] = df['monto'].astype(str).str.replace(r'[$,.]', '', regex=True)
            df['monto'] = pd.to_numeric(df['monto'], errors='coerce').fillna(0)

        return df
    except Exception as e:
        print(f"❌ Error leyendo Sheets: {e}")
        return None

