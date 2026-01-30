import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json

# --- CONFIGURACIÓN GOOGLE SHEETS ---
CREDS_JSON = os.getenv("GOOGLE_SHEETS_CREDS_JSON")
SHEET_ID = os.getenv("SPREADSHEET_ID")

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_sheet():
    creds_dict = json.loads(CREDS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # Abre la hoja por ID y selecciona la primera pestaña (Sheet1)
    sheet = client.open_by_key(SHEET_ID).sheet1
    return sheet

def guardar_en_sheets(datos_gasto):
    try:
        sheet = get_sheet()
        
        # Orden corregido para coincidir con tus columnas:
        # A: Tipo | B: Monto | C: Item | D: Categoria | E: Fecha | F: Cuenta | G: Detalle
        fila = [
            datos_gasto['tipo'],         
            datos_gasto['monto'],       
            datos_gasto['item'],
            datos_gasto['categoria'],
            datos_gasto['fecha'],
            datos_gasto['cuenta'],
            datos_gasto.get('detalle', '')
        ]

        sheet.append_row(fila)
        print(f"💾 Guardado en Sheets: {fila}")
        return True
    except Exception as e:
        print(f"❌ Error guardando en Sheets: {e}")
        return False

def obtener_gastos_mes_actual():
    """
    Descarga los datos para análisis.
    """
    print("📊 Intentando descargar datos de Sheets...")
    try:
        sheet = get_sheet()
        registros = sheet.get_all_records()
        
        print(f"📊 Registros brutos encontrados: {len(registros)}")

        if not registros:
            print("⚠️ La hoja parece estar vacía o get_all_records devolvió lista vacía.")
            return None

        df = pd.DataFrame(registros)
        
        # CHISMOSO: Imprimir las columnas que detectó Pandas
        print(f"📊 Columnas detectadas: {list(df.columns)}")

        # Limpieza básica de montos
        # Busca columnas que parezcan montos (Monto, monto, Valor, Precio)
        col_monto = None
        for col in df.columns:
            if "monto" in col.lower() or "valor" in col.lower():
                col_monto = col
                break
        
        if col_monto:
            df[col_monto] = df[col_monto].astype(str).str.replace(r'[$,.]', '', regex=True)
            df[col_monto] = pd.to_numeric(df[col_monto], errors='coerce').fillna(0)
            print(f"✅ Columna de montos '{col_monto}' procesada.")
        else:
            print("⚠️ No encontré una columna de 'Monto' o 'Valor'.")

        return df

    except Exception as e:
        print(f"❌ Error CRÍTICO leyendo Sheets: {e}")
        return None

def obtener_presupuestos():
    """
    Descarga la hoja 'Presupuestos' y la convierte en un diccionario.
    Ejemplo: {'Transporte': 50000, 'Carrete': 80000}
    """
    try:
        client = get_sheet().client # Usamos el cliente ya autenticado
        # Abrimos la hoja por ID pero buscamos la pestaña específica
        sheet = client.open_by_key(SHEET_ID).worksheet("Presupuestos")
        registros = sheet.get_all_records()
        
        presupuestos = {}
        for fila in registros:
            # Limpiamos el monto por si pusiste signos $ o puntos
            monto_limpio = str(fila['Monto']).replace('$','').replace('.','')
            if monto_limpio.isdigit():
                presupuestos[fila['Categoria'].lower()] = int(monto_limpio)
        
        return presupuestos
    except Exception as e:
        print(f"❌ Error leyendo presupuestos: {e}")
        return {}




