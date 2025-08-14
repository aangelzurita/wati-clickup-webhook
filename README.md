
# WATI → ClickUp Webhook (Render)

Despliegue sin ngrok usando Render. Mantiene tu misma lógica:
- Recibir webhook de WATI (`/wati-webhook`)
- Clonar tarea plantilla en ClickUp
- Asignar responsable
- Clonar subtareas

## Deploy en Render (Blueprint)
1. Sube estos archivos a un repo en GitHub.
2. En Render, crea **New +** → **Blueprint** y apunta a tu repo.
3. Render leerá `render.yaml` y creará el servicio.
4. Define la variable **CLICKUP_API_KEY** (no la subas al repo).
5. Render te dará una URL: `https://<tu-app>.onrender.com`
   - Tu webhook será: `POST https://<tu-app>.onrender.com/wati-webhook`

## Probar (local o con la URL de Render)
```bash
curl -X POST https://<tu-app>.onrender.com/wati-webhook       -H "Content-Type: application/json"       -d '{"acciones":"📅 Reportar Pago","name":"Juan Pérez","phone":"+5215555555555"}'
```

## Ajustes
- Cambia `LIST_ID` o IDs de plantillas/asignados en variables de entorno.
- Si quieres copiar checklists, adjuntos o campos personalizados, se puede extender.
