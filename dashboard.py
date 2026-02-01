import streamlit as st
import pandas as pd
from supabase import create_client
import plotly.express as px
from datetime import datetime

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Mis Finanzas", page_icon="💰", layout="centered")

# --- CONEXIÓN A SUPABASE ---
# Usamos st.secrets para la nube, o variables locales si estás probando
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    # Si lo corres local y no tienes secrets.toml, usa tus variables de entorno o pégalas aquí temporalmente
    import os
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

supabase = create_client(url, key)

# --- FUNCIONES ---
def cargar_datos():
    # Traemos todos los gastos ordenados por fecha
    response = supabase.table('gastos').select("*").order('fecha', desc=True).execute()
    df = pd.DataFrame(response.data)
    return df

def guardar_gasto(item, monto, categoria, cuenta, fecha):
    payload = {
        "item": item,
        "monto": monto,
        "categoria": categoria,
        "cuenta": cuenta,
        "fecha": str(fecha),
        "tipo": "Gasto"
    }
    supabase.table('gastos').insert(payload).execute()

# --- INTERFAZ GRÁFICA ---

st.title("💰 Mis Finanzas")

# 1. FORMULARIO RÁPIDO (SIDEBAR)
with st.sidebar:
    st.header("➕ Agregar Gasto")
    with st.form("nuevo_gasto"):
        item = st.text_input("¿Qué compraste?")
        monto = st.number_input("Monto", min_value=0, step=100)
        col1, col2 = st.columns(2)
        categoria = col1.selectbox("Categoría", ["Comida", "Transporte", "Regalos", "Cuentas", "Varios"])
        cuenta = col2.selectbox("Cuenta", ["Débito BICE", "Crédito BICE", "Efectivo"])
        fecha = st.date_input("Fecha", datetime.today())
        
        submitted = st.form_submit_button("Guardar Gasto")
        if submitted and item and monto > 0:
            guardar_gasto(item, monto, categoria, cuenta, fecha)
            st.success("¡Gasto guardado!")
            st.rerun() # Recarga la página para ver el cambio

# 2. CARGAR DATOS
df = cargar_datos()

if not df.empty:
    # Convertir fecha a datetime
    df['fecha'] = pd.to_datetime(df['fecha'])
    
    # Filtrar por mes actual
    mes_actual = datetime.now().month
    anio_actual = datetime.now().year
    df_mes = df[(df['fecha'].dt.month == mes_actual) & (df['fecha'].dt.year == anio_actual)]

    # 3. TARJETAS DE RESUMEN
    total_mes = df_mes['monto'].sum()
    st.metric(label=f"Gasto Total ({datetime.now().strftime('%B')})", value=f"${total_mes:,.0f}".replace(",", "."))

    # 4. GRÁFICO DE DONA (Plotly)
    if not df_mes.empty:
        fig = px.pie(df_mes, values='monto', names='categoria', hole=0.5, 
                     title="Distribución de Gastos", color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig, use_container_width=True)

    # 5. ÚLTIMOS MOVIMIENTOS
    st.subheader("📝 Últimos Movimientos")
    # Mostramos una tabla limpia
    st.dataframe(
        df[['fecha', 'item', 'categoria', 'monto', 'cuenta']].head(10),
        hide_index=True,
        column_config={
            "monto": st.column_config.NumberColumn("Monto", format="$%d"),
            "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY")
        }
    )
else:
    st.info("Aún no hay gastos registrados.")