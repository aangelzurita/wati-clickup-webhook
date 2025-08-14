
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app)  # Permite conexiones externas (WATI)

# --- Config desde variables de entorno (si no quieres, puedes hardcodear como antes) ---
CLICKUP_API_KEY = os.getenv('CLICKUP_API_KEY', 'REEMPLAZA_TU_API_KEY')
LIST_ID = os.getenv('CLICKUP_LIST_ID', '901309521629')
TEAM_ID = os.getenv('CLICKUP_TEAM_ID', '9013643983')

# Mapeo de acciones del bot a tareas y usuarios en ClickUp
# Puedes dejar los que ya tenías:
ACCIONES_TO_TAREAS = {
    "📅 Reportar Pago": {
        "tarea_id": os.getenv("TPL_REPORTE_PAGO_ID", "86a84h4xe"),
        "asignado": int(os.getenv("ASSIGNEE_REPORTE_PAGO", "87984139"))
    },
    "📊 Consultar Estado": {
        "tarea_id": os.getenv("TPL_CONSULTAR_ESTADO_ID", "86a84h4zd"),
        "asignado": int(os.getenv("ASSIGNEE_CONSULTAR_ESTADO", "126166932"))
    },
    "📄 Cesión de derechos": {
        "tarea_id": os.getenv("TPL_CESION_DERECHOS_ID", "86a84h52a"),
        "asignado": int(os.getenv("ASSIGNEE_CESION_DERECHOS", "87984139"))
    }
}

HEADERS = {
    "Authorization": CLICKUP_API_KEY,
    "Content-Type": "application/json"
}

def clonar_subtareas(original_task_id, nueva_task_id, assignee_id):
    # Render no requiere ngrok; usa la URL pública que te da Render
    # Endpoint correcto para listar subtareas por 'parent' desde una LISTA
    subtareas_url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"
    params = {"parent": original_task_id}
    subtareas_response = requests.get(subtareas_url, headers=HEADERS, params=params)

    if subtareas_response.status_code != 200:
        print("⚠️ No se pudieron obtener las subtareas:", subtareas_response.text)
        return

    subtareas = subtareas_response.json().get("tasks", [])

    for sub in subtareas:
        nueva_subtarea = {
            "name": sub.get("name", "Subtarea"),
            "description": sub.get("description", "") or "",
            "assignees": [assignee_id] if assignee_id else [],
            "tags": [tag.get("name") for tag in (sub.get("tags") or [])],
            "parent": nueva_task_id
        }

        crear_sub_url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"
        crear_sub_response = requests.post(crear_sub_url, headers=HEADERS, json=nueva_subtarea)

        if crear_sub_response.status_code in [200, 201]:
            print(f"✅ Subtarea clonada: {sub.get('name')}")
        else:
            print(f"❌ Error al clonar subtarea {sub.get('name')}: {crear_sub_response.text}")

@app.route("/", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200

@app.route('/wati-webhook', methods=['POST'])
def clonar_tarea_clickup():
    print("📩 Petición recibida:")
    try:
        data = request.get_json(force=True) or {}
        print("📦 Datos procesados:", data)

        accion = data.get("acciones") or data.get("accion") or data.get("action")
        if accion not in ACCIONES_TO_TAREAS:
            print("❌ Acción no reconocida:", accion)
            return jsonify({"error": "Acción no reconocida"}), 400

        config = ACCIONES_TO_TAREAS[accion]
        tarea_id_original = config["tarea_id"]
        assignee_id = config["asignado"]

        # 1. Obtener tarea original
        get_url = f"https://api.clickup.com/api/v2/task/{tarea_id_original}"
        original_response = requests.get(get_url, headers=HEADERS)
        if original_response.status_code != 200:
            print("❌ Error al obtener tarea:", original_response.text)
            return jsonify({"error": "No se pudo obtener la tarea original"}), 500

        original_task = original_response.json()

        # 2. Prioridad (si viene como dict o int)
        priority_value = original_task.get("priority")
        if isinstance(priority_value, dict):
            priority_value = priority_value.get("priority")
        if priority_value not in [1, 2, 3, 4]:
            priority_value = None

        # 3. Preparar datos para nueva tarea
        new_task_name = f"{original_task.get('name','Tarea')} - {data.get('name', 'Sin nombre')}"
        new_task_data = {
            "name": new_task_name,
            "description": f"Teléfono: {data.get('phone', 'Sin teléfono')}\n\n{original_task.get('description', '') or ''}",
            "tags": [t.get("name") for t in (original_task.get("tags") or [])],
            "assignees": [assignee_id] if assignee_id else []
        }
        if priority_value:
            new_task_data["priority"] = priority_value

        # Copiar estatus si existe
        status = original_task.get("status")
        if isinstance(status, dict) and status.get("status"):
            new_task_data["status"] = status["status"]
        elif isinstance(status, str) and status:
            new_task_data["status"] = status

        # 4. Crear nueva tarea clonada
        create_url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"
        create_response = requests.post(create_url, headers=HEADERS, json=new_task_data)
        print("📤 Intentando crear tarea clonada")

        if create_response.status_code in [200, 201]:
            nueva_task = create_response.json()
            nueva_task_id = nueva_task.get("id")
            print("✅ Tarea clonada con éxito. ID:", nueva_task_id)

            # 5. Agregar comentario
            comentario_url = f"https://api.clickup.com/api/v2/task/{nueva_task_id}/comment"
            comentario_body = {
                "comment_text": f"<@{assignee_id}> tienes una nueva tarea asignada automáticamente 🎯",
                "assignees": [assignee_id] if assignee_id else [],
                "rich_text": True
            }
            requests.post(comentario_url, headers=HEADERS, json=comentario_body)

            # 6. Clonar subtareas
            clonar_subtareas(tarea_id_original, nueva_task_id, assignee_id)

            return jsonify({"status": "Tarea y subtareas clonadas exitosamente", "new_task_id": nueva_task_id}), 201
        else:
            print("❌ Error al crear tarea:", create_response.text)
            return jsonify({"error": "No se pudo crear la tarea clonada"}), 500

    except Exception as e:
        import traceback
        print("🔥 Excepción:", str(e))
        traceback.print_exc()
        return jsonify({"error": "Excepción inesperada", "detalle": str(e)}), 500

# Nota: en Render se inicia con gunicorn, no hace falta app.run()
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5050)
