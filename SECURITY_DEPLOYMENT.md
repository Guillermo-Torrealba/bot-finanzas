# Seguridad del bot y dashboard

## Configuración obligatoria del bot

Configura secretos solo en el gestor de secretos del host:

- `META_APP_SECRET`: secreto de la app de Meta para validar `X-Hub-Signature-256`.
- `VERIFY_TOKEN`: valor aleatorio usado únicamente para verificar el webhook de Meta.
- `APPLE_PAY_WEBHOOK_TOKEN`: credencial aleatoria para el endpoint legado `/apple-pay`.
- `TOKEN_WHATSAPP`, `PHONE_NUMBER_ID`, `SUPABASE_URL`, `SUPABASE_KEY` y `OPENAI_API_KEY`.

El POST `/webhook` devuelve error si falta el secreto Meta o si la firma no es
válida. `/apple-pay` queda cerrado si no tiene credencial. No se debe habilitar
ese endpoint hasta confirmar y actualizar todos sus llamadores; no se encontró
un llamador dentro de los repositorios locales revisados. El token de
verificación GET de Meta no autentica POST.

`SUPABASE_KEY` y `OPENAI_API_KEY` son secretos de servidor. No deben incluirse
en el cliente móvil, el dashboard ni el repositorio. Para el dashboard se usa
`SUPABASE_PUBLISHABLE_KEY` o una clave JWT legacy con `role=anon`, junto con el
login individual de Supabase Auth. El dashboard rechaza claves de servicio.

## Límites pendientes antes de desplegar

- Confirmar el host del bot y configurar los secretos anteriores sin pegarlos
  en GitHub, código, chat o logs.
- Actualizar o deshabilitar el caller externo de `/apple-pay` antes de activar
  su token.
- Configurar el dashboard con la clave pública y verificar RLS desde una cuenta
  autenticada de usuario. La clave de servicio no es válida para esa aplicación.
- La rama local usa `claim_whatsapp_message` para deduplicar IDs en PostgreSQL y
  limita la cola a 32 mensajes/4 workers. La migración
  `20261028193600_whatsapp_webhook_message_deduplication.sql` ya se aplicó en
  producción y se comprobó que solo `service_role` ejecuta la RPC. La tabla
  guarda solo el ID del mensaje y lo elimina tras 30 días.
- El alta antigua aceptaba un teléfono escrito por la persona sin verificar
  propiedad. La app local ya no crea ese vínculo y el bot solo acepta filas con
  `verified_at` no nulo. La migración
  `20261028193700_require_verified_whatsapp_phone.sql` ya revocó el acceso
  cliente y agregó el marcador; la asociación existente sigue sin verificar.
  Falta implementar un flujo de verificación del teléfono y desplegar este bot;
  los teléfonos no verificados deben rechazarse.
- Cada mensaje debe corresponder exactamente a un `user_id` registrado antes
  de transcribir audio, llamar a OpenAI o escribir un movimiento; mensajes sin
  asociación única se rechazan.
- Rotar cualquier secreto que haya estado en un commit, log o configuración
  compartida, y verificar los logs de uso del proveedor correspondiente.

Estos cambios son código local y no despliegan ni rotan secretos en el host.
