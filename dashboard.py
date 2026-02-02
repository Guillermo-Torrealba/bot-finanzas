import streamlit as st
import pandas as pd
from supabase import create_client
import plotly.express as px
from datetime import datetime
import calendar

# --- CONFIGURACIÓN DE PÁGINA (ESTILO MONEYBOARD) ---
st.set_page_config(page_title="Mis Finanzas Pro", page_icon="💳", layout="wide")

# --- CONEXIÓN SUPABASE ---
try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except:
    import os
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

supabase = create_client(url, key)

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_datos():
    # Traemos todo. En una app real masiva, filtrarías por fecha en la query.
    response = supabase.table('gastos').select("*").order('fecha', desc=True).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df['fecha'] = pd.to_datetime(df['fecha'])
        df['monto'] = pd.to_numeric(df['monto'])
    return df

def guardar_movimiento(item, monto, categoria, cuenta, fecha, tipo):
    # Si es Gasto, guardamos el monto tal cual (la lógica de resta se hace visualmente)
    # Opcional: Podríamos guardarlo negativo, pero mejor mantenerlo positivo y restar en la UI
    payload = {
        "item": item,
        "monto": monto,
        "categoria": categoria,
        "cuenta": cuenta,
        "fecha": str(fecha),
        "tipo": tipo
    }
    supabase.table('gastos').insert(payload).execute()

def actualizar_registro(changes, df_original):
    # Procesar ediciones de la tabla interactiva
    for index, row_changes in changes['edited_rows'].items():
        id_registro = df_original.iloc[index]['id']
        # Convertimos el int64 de pandas a int nativo de python para JSON
        if 'id' in row_changes: del row_changes['id'] 
        
        supabase.table('gastos').update(row_changes).eq('id', int(id_registro)).execute()
    
    # Procesar borrados
    for index in changes['deleted_rows']:
        id_registro = df_original.iloc[index]['id']
        supabase.table('gastos').delete().eq('id', int(id_registro)).execute()

# --- INTERFAZ SIDEBAR (Filtros y Carga) ---
with st.sidebar:
    st.title("🎛 Filtros")
    
    # Selector de Fecha Inteligente
    hoy = datetime.now()
    anio_sel = st.selectbox("Año", range(hoy.year, 2023, -1))
    meses = list(calendar.month_name)[1:] # Enero a Diciembre
    mes_sel = st.selectbox("Mes", meses, index=hoy.month - 1)
    
    # Convertir nombre de mes a número
    mes_num = meses.index(mes_sel) + 1

# --- CARGA DE DATOS ---
df = cargar_datos()

# --- FORMULARIO DE INGRESO (ARRIBA) ---
with st.expander("➕ Nuevo Movimiento (Gasto o Ingreso)", expanded=False):
    with st.form("nuevo_form"):
        col1, col2, col3, col4 = st.columns(4)
        tipo = col1.selectbox("Tipo", ["Gasto", "Ingreso"])
        monto = col2.number_input("Monto", min_value=0, step=1000)
        item = col3.text_input("Concepto (Ej: Uber, Sueldo)")
        fecha = col4.date_input("Fecha", datetime.today())
        
        col5, col6 = st.columns(2)
        
        # Categorías dinámicas según el tipo
        if tipo == "Gasto":
            cats = ["Comida", "Transporte", "Hogar", "Ocio", "Salud", "Cuentas", "Varios"]
        else:
            cats = ["Sueldo", "Freelance", "Regalo", "Ventas", "Inversión"]
            
        categoria = col5.selectbox("Categoría", cats)
        cuenta = col6.selectbox("Cuenta", ["Débito BICE", "Crédito BICE", "Efectivo", "Cuenta RUT"])
        
        if st.form_submit_button("💾 Guardar Movimiento"):
            guardar_movimiento(item, monto, categoria, cuenta, fecha, tipo)
            st.success("Guardado exitosamente")
            st.rerun()

# --- LÓGICA DE FILTRADO Y DASHBOARD ---
if not df.empty:
    # 1. Filtrar por el Mes seleccionado
    df_filtrado = df[
        (df['fecha'].dt.year == anio_sel) & 
        (df['fecha'].dt.month == mes_num)
    ]
    
    # 2. Calcular Totales
    ingresos = df_filtrado[df_filtrado['tipo'] == 'Ingreso']['monto'].sum()
    gastos = df_filtrado[df_filtrado['tipo'] == 'Gasto']['monto'].sum()
    balance = ingresos - gastos

    # 3. Mostrar Tarjetas Estilo "MoneyBoard"
    st.divider()
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("📉 Gastos", f"${gastos:,.0f}", delta_color="inverse")
    kpi2.metric("📈 Ingresos", f"${ingresos:,.0f}")
    kpi3.metric("💰 Balance Mensual", f"${balance:,.0f}", delta=f"{balance:,.0f}")
    st.divider()

    # 4. TABS: Gráficos | Edición
    tab1, tab2 = st.tabs(["📊 Análisis Visual", "📝 Editar/Borrar Registros"])

    with tab1:
        if not df_filtrado.empty:
            col_graph1, col_graph2 = st.columns(2)
            
            # Gráfico de Dona (Gastos)
            df_gastos = df_filtrado[df_filtrado['tipo'] == 'Gasto']
            if not df_gastos.empty:
                fig_gastos = px.pie(df_gastos, values='monto', names='categoria', hole=0.4, 
                                  title="Gastos por Categoría", color_discrete_sequence=px.colors.qualitative.Pastel)
                col_graph1.plotly_chart(fig_gastos, use_container_width=True)
            
            # Gráfico de Barras (Diario)
            df_diario = df_filtrado.groupby(df_filtrado['fecha'].dt.day)['monto'].sum().reset_index()
            fig_barras = px.bar(df_diario, x='fecha', y='monto', title="Evolución Diaria", 
                                labels={'fecha': 'Día', 'monto': 'Monto ($)'})
            col_graph2.plotly_chart(fig_barras, use_container_width=True)
        else:
            st.info(f"No hay movimientos en {mes_sel} {anio_sel}")

    with tab2:
        st.subheader("Gestión de Movimientos")
        st.caption("💡 Haz doble clic en una celda para editar. Selecciona la fila y presiona 'Del' en tu teclado para borrar.")
        
        # TABLA INTERACTIVA (DATA EDITOR)
        # Mostramos todas las columnas excepto created_at o detalles técnicos
        columnas_visibles = ['id', 'fecha', 'item', 'categoria', 'monto', 'tipo', 'cuenta']
        
        df_editor = st.data_editor(
            df_filtrado[columnas_visibles],
            column_config={
                "monto": st.column_config.NumberColumn("Monto", format="$%d"),
                "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=["Gasto", "Ingreso"]),
                "categoria": st.column_config.SelectboxColumn("Categoría", options=["Comida", "Transporte", "Hogar", "Ocio", "Sueldo", "Varios"]),
            },
            hide_index=True,
            num_rows="dynamic", # Permite agregar/borrar filas visualmente
            key="editor_datos"
        )
        
        # BOTÓN PARA GUARDAR CAMBIOS
        if st.button("💾 Aplicar Cambios (Editar/Borrar)"):
            # Streamlit guarda los cambios en st.session_state['editor_datos']
            changes = st.session_state['editor_datos']
            
            if changes['edited_rows'] or changes['deleted_rows'] or changes['added_rows']:
                try:
                    # Nota: Para 'added_rows' es mejor usar el formulario de arriba, 
                    # aquí nos enfocamos en update/delete para no complicar la lógica
                    actualizar_registro(changes, df_filtrado)
                    st.success("Cambios sincronizados con la nube ☁️")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
            else:
                st.info("No detecté cambios para guardar.")

else:
    st.warning("No hay datos cargados. Agrega tu primer movimiento arriba.")