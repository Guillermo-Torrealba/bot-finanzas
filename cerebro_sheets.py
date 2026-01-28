import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

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