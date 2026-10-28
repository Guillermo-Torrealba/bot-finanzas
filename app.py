import hashlib
import hmac
import os
import re
import secrets
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from flask import Flask, request
import requests
# AGREGADO: 'analizar_consulta'
from cerebro_chatgpt import interpretar_gasto, normalizar_cuenta, transcribir_audio, analizar_consulta
# AGREGADO: 'obtener_ultimos_gastos'
from cerebro_supabase import guardar_gasto, supabase, obtener_ultimos_gastos
from datetime import datetime
from decimal import Decimal, InvalidOperation

app = Flask(__name__)

# --- TUS DATOS ---
TOKEN_WHATSAPP = os.getenv("TOKEN_WHATSAPP")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
META_APP_SECRET = os.getenv("META_APP_SECRET")
APPLE_PAY_WEBHOOK_TOKEN = os.getenv("APPLE_PAY_WEBHOOK_TOKEN")

app.config["MAX_CONTENT_LENGTH"] = 256 * 1024

memoria_usuarios = {} 
_message_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="whatsapp")
_message_slots = threading.BoundedSemaphore(32)


def _claim_whatsapp_message(message_id):
    if not supabase or not isinstance(message_id, str):
        return None
    try:
        response = supabase.rpc(
            "claim_whatsapp_message", {"p_message_id": message_id}
        ).execute()
        return response.data is True
    except Exception as e:
        print(f"❌ Error reservando mensaje ({type(e).__name__}).")
        return None


def _process_message_and_release_slot(*args):
    try:
        procesar_mensaje_background(*args)
    finally:
        _message_slots.release()

# --- LA BIENVENIDA ---
@app.route("/")
def home():
    return "¡Hola! El bot de finanzas está VIVO y ESCUCHANDO 🤖🎧", 200

# --- FUNCIÓN: DESCARGAR AUDIO ---
def descargar_audio_whatsapp(media_id):
    if not TOKEN_WHATSAPP or not re.fullmatch(r"[0-9]+", str(media_id)):
        return None
    ruta_temporal = None
    try:
        url_info = f"https://graph.facebook.com/v21.0/{media_id}"
        headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}"}
        resp_info = requests.get(url_info, headers=headers, timeout=(5, 15))
        
        if resp_info.status_code != 200:
            print(f"❌ Error consultando audio de WhatsApp ({resp_info.status_code}).")
            return None
            
        url_media = resp_info.json().get("url")
        parsed_media_url = urlparse(url_media or "")
        host = parsed_media_url.hostname or ""
        trusted_media_host = (
            host == "graph.facebook.com"
            or host.endswith(".facebook.com")
            or host.endswith(".fbcdn.net")
            or host.endswith(".fbsbx.com")
        )
        if (
            parsed_media_url.scheme != "https"
            or not trusted_media_host
            or parsed_media_url.username is not None
            or parsed_media_url.password is not None
            or parsed_media_url.port not in (None, 443)
        ):
            return None
        headers_media = {"Authorization": f"Bearer {TOKEN_WHATSAPP}", "User-Agent": "Mozilla/5.0"}
        total_bytes = 0
        with requests.get(
            url_media, headers=headers_media, timeout=(5, 20), stream=True
        ) as resp_media:
            resp_media.raise_for_status()
            with tempfile.NamedTemporaryFile(
                prefix="finanzas_audio_", suffix=".ogg", delete=False
            ) as archivo:
                ruta_temporal = archivo.name
                for chunk in resp_media.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > 20_000_000:
                        raise ValueError("Audio demasiado grande.")
                    archivo.write(chunk)
        if total_bytes == 0:
            os.remove(ruta_temporal)
            return None
        return ruta_temporal
    except Exception as e:
        if ruta_temporal:
            try:
                os.remove(ruta_temporal)
            except OSError:
                pass
        print(f"❌ Error descargando audio ({type(e).__name__}).")
        return None

# --- CEREBRO EN SEGUNDO PLANO (MODIFICADO) ---
def procesar_mensaje_background(numero, texto_usuario, tipo_mensaje, mensaje_id, audio_id=None):
    print(f"🔄 Procesando... (Tipo: {tipo_mensaje})")

    # Resolve a single registered owner before sending any message/audio to AI
    # or using the server-side Supabase client.
    try:
        resp_usuario = (
            supabase.table("usuarios_bot")
            .select("user_id")
            .eq("celular", numero)
            .not_.is_("verified_at", "null")
            .execute()
        )
        if len(resp_usuario.data or []) != 1:
            enviar_whatsapp(numero, "🔒 No pude vincular este número a una cuenta registrada.")
            return
        user_id_detectado = resp_usuario.data[0].get("user_id")
        if not user_id_detectado:
            enviar_whatsapp(numero, "🔒 No pude validar la cuenta asociada a este número.")
            return
    except Exception as e:
        print(f"❌ Error buscando identidad ({type(e).__name__}).")
        enviar_whatsapp(numero, "No pude validar tu cuenta ahora. Inténtalo nuevamente.")
        return
    
    # --- 1. BLOQUE DE AUDIO ---
    if (tipo_mensaje == "audio" or tipo_mensaje == "voice") and audio_id:
        enviar_whatsapp(numero, "🎧 Escuchando...")
        archivo_temporal = descargar_audio_whatsapp(audio_id)
        
        if archivo_temporal:
            texto_transcrito = transcribir_audio(archivo_temporal)
            try:
                os.remove(archivo_temporal)
            except:
                pass
            texto_usuario = texto_transcrito 
        else:
            enviar_whatsapp(numero, "❌ No pude descargar el audio de WhatsApp.")
            return

    if not texto_usuario:
        return

    # --- 3. LÓGICA DE GASTOS Y PREGUNTAS ---
    try:
        # CASO A: EL USUARIO ESTÁ RESPONDIENDO (HILO DE CONVERSACIÓN)
        if numero in memoria_usuarios:
            contexto = memoria_usuarios[numero]

            # PASO 1: Recibimos el nombre limpio del gasto (Item)
            if contexto.get("step") == "esperando_item_apple":
                contexto["item_limpio"] = texto_usuario
                contexto["step"] = "esperando_metodo_apple" # Pasamos al siguiente paso
                enviar_whatsapp(numero, "Perfecto. ¿Fue con **Débito** o **Crédito**?")
                return # Salimos para esperar la siguiente respuesta

            # PASO 2: Recibimos el método de pago y guardamos todo
            elif contexto.get("step") == "esperando_metodo_apple":
                print("✅ Finalizando registro Apple Pay.")
                
                # Usamos tu lógica de IA para categorizar según el item limpio
                frase_para_ia = f"Gaste {contexto['monto']} en {contexto['item_limpio']}"
                analisis_ia = interpretar_gasto(frase_para_ia)
                
                categoria = "Varios"
                if analisis_ia.get("gastos"):
                    categoria = analisis_ia["gastos"][0]["categoria"]

                # Armamos el objeto final como querías
                gasto_final = {
                    "fecha": datetime.now().strftime("%Y-%m-%d"),
                    "monto": int(float(contexto["monto"])), # Limpieza de número
                    "item": contexto["item_limpio"],        # Tu respuesta limpia (Café)
                    "detalle": contexto["detalle"],         # El nombre del iPhone (Sociedad X)
                    "categoria": categoria,
                    "cuenta": "Banco BICE",
                    "metodo_pago": "Crédito" if "cred" in texto_usuario.lower() else "Débito",
                    "tipo": "Gasto",
                    "user_id": user_id_detectado
                }

                exito = guardar_gasto(gasto_final)
                del memoria_usuarios[numero] # Limpiamos memoria

                if exito:
                    enviar_whatsapp(numero, f"✅ Guardado: **{gasto_final['item']}** (${gasto_final['monto']}) pagado con {gasto_final['metodo_pago']}.")
                else:
                    enviar_whatsapp(numero, "❌ Error al guardar en la base de datos.")

            # >>> SUB-CASO A.2: ES RESPUESTA DE GASTO NORMAL (Completar cuenta) <<<
            else:
                gasto_pendiente = contexto
                cuenta_limpia = normalizar_cuenta(texto_usuario)
                gasto_pendiente['cuenta'] = cuenta_limpia
                
                # INYECTAMOS EL ID
                gasto_pendiente['user_id'] = user_id_detectado

                exito = guardar_gasto(gasto_pendiente) 
                del memoria_usuarios[numero]
                
                if exito:
                    enviar_whatsapp(numero, f"✅ Listo. ${gasto_pendiente['monto']} en **{cuenta_limpia}**.")
                else:
                    enviar_whatsapp(numero, "❌ Hubo un error guardando en Supabase.")
        
        # CASO B: MENSAJE NUEVO
        else:
            respuesta_ia = interpretar_gasto(texto_usuario)
            
            # --- NUEVA LÓGICA: ¿ES PREGUNTA O GASTO? ---
            if respuesta_ia.get("intencion") == "pregunta":
                if not user_id_detectado:
                    enviar_whatsapp(numero, "🔒 Necesito saber quién eres para analizar tus datos. (Tu número no está registrado).")
                else:
                    enviar_whatsapp(numero, "🧐 Déjame revisar tus números...")
                    # 1. Traemos los datos de Supabase
                    datos_gastos = obtener_ultimos_gastos(user_id_detectado)
                    # 2. Analizamos con GPT
                    respuesta_analisis = analizar_consulta(texto_usuario, datos_gastos)
                    # 3. Respondemos
                    enviar_whatsapp(numero, respuesta_analisis)

            # --- LÓGICA ANTIGUA (Es un gasto) ---
            elif respuesta_ia.get("gastos"):
                gasto = respuesta_ia["gastos"][0]
                
                # INYECTAMOS EL ID
                gasto['user_id'] = user_id_detectado
                
                if gasto['monto'] == 0:
                    enviar_whatsapp(numero, f"👂 Escuché: '{texto_usuario}'\n🤷‍♂️ Pero no entendí el monto.")
                
                elif not gasto.get('cuenta'):
                    memoria_usuarios[numero] = gasto
                    enviar_whatsapp(numero, f"🤔 Entendido: {gasto['item']} (${gasto['monto']}).\n\n¿Con qué pagaste?")
                
                else:
                    exito = guardar_gasto(gasto)

                    if exito:
                        enviar_whatsapp(numero, f"✅ Listo! {gasto['item']} (${gasto['monto']}) anotado en {gasto['cuenta']}.")
                    else:
                        enviar_whatsapp(numero, "❌ Error guardando en la base de datos.")
            
            # CASO C: NO ENTENDIÓ NADA
            else:
                enviar_whatsapp(numero, "👋 No entendí si es un gasto o una pregunta.")

    except Exception as e:
        print(f"❌ Error lógica ({type(e).__name__}).")

# --- WEBHOOK ---
@app.route("/webhook", methods=["GET"])
def verificar_token():
    if not VERIFY_TOKEN:
        return "Verificación no configurada", 503
    supplied_token = request.args.get("hub.verify_token", "")
    if secrets.compare_digest(supplied_token, VERIFY_TOKEN):
        return request.args.get("hub.challenge")
    return "Token inválido", 403


def _meta_signature_is_valid(raw_body: bytes, signature: str | None) -> bool:
    if not META_APP_SECRET or not signature:
        return False
    if not re.fullmatch(r"sha256=[0-9a-fA-F]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    if not META_APP_SECRET:
        return "Webhook no configurado", 503
    raw_body = request.get_data(cache=True)
    if not _meta_signature_is_valid(
        raw_body, request.headers.get("X-Hub-Signature-256")
    ):
        return "Firma inválida", 401

    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return "JSON inválido", 400
    try:
        if datos.get("object") == "whatsapp_business_account":
            entradas = datos.get("entry")
            if not isinstance(entradas, list):
                return "Evento inválido", 400
            for entrada_raiz in entradas:
                cambios = entrada_raiz.get("changes", []) if isinstance(entrada_raiz, dict) else []
                if not isinstance(cambios, list):
                    continue
                for cambio in cambios:
                    valor = cambio.get("value", {}) if isinstance(cambio, dict) else {}
                    mensajes = valor.get("messages", []) if isinstance(valor, dict) else []
                    if not isinstance(mensajes, list):
                        continue
                    for mensaje in mensajes:
                        if not isinstance(mensaje, dict):
                            continue
                        msg_id = mensaje.get("id")
                        numero = mensaje.get("from")
                        tipo = mensaje.get("type")
                        if not all(isinstance(value, str) and value for value in (msg_id, numero, tipo)):
                            return "Mensaje inválido", 400

                        texto_usuario = ""
                        audio_id = None
                        if tipo == "text":
                            text_payload = mensaje.get("text", {})
                            texto_usuario = text_payload.get("body", "") if isinstance(text_payload, dict) else ""
                            if not isinstance(texto_usuario, str):
                                return "Mensaje inválido", 400
                        elif tipo == "audio":
                            audio_payload = mensaje.get("audio", {})
                            audio_id = audio_payload.get("id") if isinstance(audio_payload, dict) else None
                        elif tipo == "voice":
                            voice_payload = mensaje.get("voice", {})
                            audio_id = voice_payload.get("id") if isinstance(voice_payload, dict) else None

                        if not texto_usuario and not audio_id:
                            continue
                        if not _message_slots.acquire(blocking=False):
                            return "Capacidad temporalmente agotada", 503

                        claimed = _claim_whatsapp_message(msg_id)
                        if claimed is None:
                            _message_slots.release()
                            return "No se pudo reservar el mensaje", 503
                        if not claimed:
                            _message_slots.release()
                            continue

                        try:
                            _message_executor.submit(
                                _process_message_and_release_slot,
                                numero,
                                texto_usuario,
                                tipo,
                                msg_id,
                                audio_id,
                            )
                        except RuntimeError:
                            _message_slots.release()
                            print("❌ No se pudo iniciar el procesador de mensajes.")
                            return "Procesamiento temporalmente no disponible", 503

        return "EVENT_RECEIVED", 200
    except Exception as e:
        print(f"❌ Error webhook ({type(e).__name__}).")
        return "EVENT_RECEIVED", 200

def enviar_whatsapp(numero, texto):
    if not TOKEN_WHATSAPP or not PHONE_NUMBER_ID:
        print("Error: falta configuración de WhatsApp.")
        return
    try:
        url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {TOKEN_WHATSAPP}", "Content-Type": "application/json"}
        data = {"messaging_product": "whatsapp", "to": numero, "type": "text", "text": {"body": texto}}
        response = requests.post(url, headers=headers, json=data, timeout=(5, 15))
        if response.status_code >= 400:
            print(f"Error de WhatsApp API ({response.status_code}).")
    except Exception as e:
        print(f"Error enviando WhatsApp ({type(e).__name__}).")

@app.route("/apple-pay", methods=["POST"])
def apple_pay_trigger():
    if not APPLE_PAY_WEBHOOK_TOKEN:
        return "Webhook no configurado", 503
    supplied_token = request.headers.get("Authorization", "")
    expected_token = f"Bearer {APPLE_PAY_WEBHOOK_TOKEN}"
    if not secrets.compare_digest(supplied_token, expected_token):
        return "No autorizado", 401

    try:
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            return "JSON inválido", 400
        telefono = datos.get("telefono")
        monto = datos.get("monto", "0")
        comercio = datos.get("comercio", "Comercio desconocido")
        
        if not isinstance(telefono, str):
            return "Teléfono inválido", 400
        telefono = telefono.removeprefix("+")
        if not re.fullmatch(r"[1-9]\d{7,14}", telefono):
            return "Teléfono inválido", 400
        try:
            monto_numero = Decimal(str(monto))
        except (InvalidOperation, TypeError, ValueError):
            return "Monto inválido", 400
        if (
            not monto_numero.is_finite()
            or monto_numero != monto_numero.to_integral_value()
            or not 0 < monto_numero <= 100_000_000
        ):
            return "Monto inválido", 400
        if not isinstance(comercio, str) or not comercio.strip() or len(comercio) > 120:
            return "Comercio inválido", 400

        if not supabase:
            return "Servicio temporalmente no disponible", 503
        usuario = (
            supabase.table("usuarios_bot")
            .select("user_id")
            .eq("celular", telefono)
            .not_.is_("verified_at", "null")
            .execute()
        )
        if len(usuario.data or []) != 1 or not usuario.data[0].get("user_id"):
            return "Número no registrado", 404

        # Guardamos los datos iniciales y saltamos al paso de preguntar el ITEM
        memoria_usuarios[telefono] = {
            "monto": int(monto_numero),
            "detalle": comercio.strip(),   # El nombre legal va al detalle
            "step": "esperando_item_apple" # Nueva etapa
        }

        mensaje = f"💸 Detecté un pago de **${int(monto_numero)}** en _{comercio.strip()}_.\n\n¿Qué compraste? (Ej: Café, Almuerzo, Regalo)"
        enviar_whatsapp(telefono, mensaje)
        
        return "OK", 200
    except Exception as e:
        print(f"❌ Error Apple Pay ({type(e).__name__}).")
        return "Error", 500


if __name__ == "__main__":
    app.run(port=5000)
