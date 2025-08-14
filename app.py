
import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

def env_int(key, default=0):
    try:
        val = os.getenv(key, str(default)).strip()
        if val == "":
            return int(default)
        return int(val)
    except Exception:
        return int(default)

def env_str(key, default=""):
    val = os.getenv(key, default)
    return (val or default).strip()

app = Flask(__name__)
CORS(app)

CLICKUP_API_KEY = env_str('CLICKUP_API_KEY', '')
LIST_ID = env_str('CLICKUP_LIST_ID', '')
TEAM_ID = env_str('CLICKUP_TEAM_ID', '')

ACCIONES_TO_TAREAS = {
    "📅 Reportar Pago": {
        "tarea_id": env_str("TPL_REPORTE_PAGO_ID", ""),
        "asignado": env_int("ASSIGNEE_REPORTE_PAGO", 0)
    },
    "📊 Consultar Estado": {
        "tarea_id": env_str("TPL_CONSULTAR_ESTADO_ID", ""),
        "asignado": env_int("ASSIGNEE_CONSULTAR_ESTADO", 0)
    },
    "📄 Cesión de derechos": {
        "tarea_id": env_str("TPL_CESION_DERECHOS_ID", ""),
        "asignado": env_int("ASSIGNEE_CESION_DERECHOS", 0)
    },
    "🧾 Facturar Pagos": {
        "tarea_id": env_str("TPL_FACTURAR_PAGOS_ID", ""),
        "asignado": env_int("ASSIGNEE_FACTURAR_PAGOS", 0)
    },
    "🚀 Nueva Inversión": {
        "tarea_id": env_str("TPL_NUEVA_INVERSION_ID", ""),
        "asignado": env_int("ASSIGNEE_NUEVA_INVERSION", 0)
    },
    "💲 Precio Actualizado": {
        "tarea_id": env_str("TPL_PRECIO_ACTUALIZADO_ID", ""),
        "asignado": env_int("ASSIGNEE_PRECIO_ACTUALIZADO", 0)
    },
    "⚖️ Asesoría personal": {
        "tarea_id": env_str("TPL_ASESORIA_PERSONAL_ID", ""),
        "asignado": env_int("ASSIGNEE_ASESORIA_PERSONAL", 0)
    },
    "👥 Referidos +2%": {
        "tarea_id": env_str("TPL_REFERIDOS_ID", ""),
        "asignado": env_int("ASSIGNEE_REFERIDOS", 0)
    }
}


HEADERS = {
    "Authorization": CLICKUP_API_KEY,
    "Content-Type": "application/json"
}

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "has_key": bool(CLICKUP_API_KEY),
        "list_id_set": bool(LIST_ID),
        "tpls": {k: bool(v.get("tarea_id")) for k, v in ACCIONES_TO_TAREAS.items()}
    }), 200

def log(msg):
    print(msg, flush=True)

def _get_task(task_id):
    url = f"https://api.clickup.com/api/v2/task/{task_id}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        raise RuntimeError(f"GET task {task_id} failed: {r.status_code} {r.text}")
    return r.json()

def _create_task(payload):
    url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"
    r = requests.post(url, headers=HEADERS, json=payload)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"CREATE task failed: {r.status_code} {r.text}")
    return r.json()

def _comment(task_id, text, assignees=None):
    url = f"https://api.clickup.com/api/v2/task/{task_id}/comment"
    body = {"comment_text": text, "rich_text": True}
    if assignees:
        body["assignees"] = assignees
    r = requests.post(url, headers=HEADERS, json=body)
    return r.status_code in (200, 201)

def _list_subtasks(parent_task_id, page=0):
    url = f"https://api.clickup.com/api/v2/list/{LIST_ID}/task"
    params = {"parent": parent_task_id, "page": page}
    r = requests.get(url, headers=HEADERS, params=params)
    if r.status_code != 200:
        raise RuntimeError(f"LIST subtasks for {parent_task_id} failed: {r.status_code} {r.text}")
    data = r.json()
    return data.get("tasks", []), data.get("last_page", True)

def _priority_val(p):
    if isinstance(p, int) and p in (1,2,3,4):
        return p
    if isinstance(p, dict):
        v = p.get("priority")
        if isinstance(v, int) and v in (1,2,3,4):
            return v
    return None

def clonar_subtareas(original_task_id, nueva_task_id, assignee_id):
    page = 0
    while True:
        tasks, last = _list_subtasks(original_task_id, page=page)
        for sub in tasks:
            payload = {
                "name": sub.get("name") or "Subtarea",
                "description": sub.get("description") or "",
                "assignees": [assignee_id] if assignee_id else [],
                "tags": [t.get("name") for t in (sub.get("tags") or [])],
                "parent": nueva_task_id
            }
            pr = _priority_val(sub.get("priority"))
            if pr:
                payload["priority"] = pr
            _create_task(payload)
            log(f"✅ Subtarea clonada: {sub.get('name')}")
        if last:
            break
        page += 1

@app.route("/wati-webhook", methods=["POST"])
def wati():
    try:
        data = request.get_json(force=True) or {}
        log("📦 Datos procesados: " + json.dumps(data, ensure_ascii=False))

        if not CLICKUP_API_KEY:
            return jsonify({"error": "CLICKUP_API_KEY no configurado"}), 500
        if not LIST_ID:
            return jsonify({"error": "CLICKUP_LIST_ID no configurado"}), 500

        accion = data.get("acciones") or data.get("accion") or data.get("action")
        if not accion or accion not in ACCIONES_TO_TAREAS:
            return jsonify({"error": "Acción no reconocida", "accion": accion}), 400

        cfg = ACCIONES_TO_TAREAS[accion]
        plantilla_id = cfg.get("tarea_id")
        assignee_id = cfg.get("asignado") or 0
        if not plantilla_id:
            return jsonify({"error": "TPL_ID no configurado para esta acción"}), 400

        plantilla = _get_task(plantilla_id)
        pr = _priority_val(plantilla.get("priority"))
        tags = [t.get("name") for t in (plantilla.get("tags") or [])]
        nombre = data.get("name") or data.get("nombre") or "Sin nombre"
        telefono = data.get("phone") or data.get("telefono") or "Sin teléfono"

        payload = {
            "name": f"{plantilla.get('name','Tarea')} - {nombre}",
            "description": f"Teléfono: {telefono}\n\n{plantilla.get('description') or ''}",
            "tags": tags,
            "assignees": [assignee_id] if assignee_id else []
        }
        if pr:
            payload["priority"] = pr

        nueva = _create_task(payload)
        nueva_id = nueva.get("id")

        if assignee_id:
            _comment(nueva_id, f"<@{assignee_id}> nueva tarea creada automáticamente.", [assignee_id])
        else:
            _comment(nueva_id, "Nueva tarea creada automáticamente desde WATI.")

        clonar_subtareas(plantilla_id, nueva_id, assignee_id)
        return jsonify({"status": "Tarea y subtareas clonadas exitosamente", "new_task_id": nueva_id}), 201

    except Exception as e:
        log(f"🔥 Error: {e}")
        return jsonify({"error": str(e)}), 500
