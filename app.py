import os
import sqlite3
from datetime import date

from flask import Flask, g, jsonify, redirect, render_template, request, url_for

DB_PATH = os.environ.get("DB_PATH", "/data/registro.db")
API_TOKEN = os.environ.get("API_TOKEN", "")

app = Flask(__name__)

ESTADOS = ["Activo", "En pausa", "Finalizado"]


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS tecnicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            especialidad TEXT
        );

        CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            cliente TEXT,
            ubicacion TEXT
        );

        CREATE TABLE IF NOT EXISTS asignaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tecnico_id INTEGER NOT NULL REFERENCES tecnicos(id) ON DELETE CASCADE,
            proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
            rol TEXT,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT,
            estado TEXT NOT NULL DEFAULT 'Activo'
        );
        """
    )
    db.commit()


with app.app_context():
    init_db()


@app.route("/")
def inicio():
    db = get_db()
    filtro = request.args.get("estado", "Activo")

    sql = """
        SELECT a.id, a.rol, a.fecha_inicio, a.fecha_fin, a.estado,
               t.nombre AS tecnico, t.especialidad,
               p.nombre AS proyecto, p.cliente, p.ubicacion
        FROM asignaciones a
        JOIN tecnicos t ON t.id = a.tecnico_id
        JOIN proyectos p ON p.id = a.proyecto_id
    """
    params = []
    if filtro in ESTADOS:
        sql += " WHERE a.estado = ?"
        params.append(filtro)
    sql += " ORDER BY p.nombre, t.nombre"

    return render_template(
        "index.html",
        asignaciones=db.execute(sql, params).fetchall(),
        tecnicos=db.execute("SELECT * FROM tecnicos ORDER BY nombre").fetchall(),
        proyectos=db.execute("SELECT * FROM proyectos ORDER BY nombre").fetchall(),
        estados=ESTADOS,
        filtro=filtro,
        hoy=date.today().isoformat(),
    )


@app.post("/tecnicos")
def crear_tecnico():
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO tecnicos (nombre, especialidad) VALUES (?, ?)",
        (request.form["nombre"].strip(), request.form.get("especialidad", "").strip()),
    )
    db.commit()
    return redirect(url_for("inicio"))


@app.post("/proyectos")
def crear_proyecto():
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO proyectos (nombre, cliente, ubicacion) VALUES (?, ?, ?)",
        (
            request.form["nombre"].strip(),
            request.form.get("cliente", "").strip(),
            request.form.get("ubicacion", "").strip(),
        ),
    )
    db.commit()
    return redirect(url_for("inicio"))


@app.post("/asignaciones")
def crear_asignacion():
    db = get_db()
    db.execute(
        """INSERT INTO asignaciones (tecnico_id, proyecto_id, rol, fecha_inicio, estado)
           VALUES (?, ?, ?, ?, 'Activo')""",
        (
            request.form["tecnico_id"],
            request.form["proyecto_id"],
            request.form.get("rol", "").strip(),
            request.form.get("fecha_inicio") or date.today().isoformat(),
        ),
    )
    db.commit()
    return redirect(url_for("inicio"))


@app.post("/asignaciones/<int:asignacion_id>/estado")
def cambiar_estado(asignacion_id):
    nuevo = request.form["estado"]
    if nuevo not in ESTADOS:
        return redirect(url_for("inicio"))
    db = get_db()
    fecha_fin = date.today().isoformat() if nuevo == "Finalizado" else None
    db.execute(
        "UPDATE asignaciones SET estado = ?, fecha_fin = ? WHERE id = ?",
        (nuevo, fecha_fin, asignacion_id),
    )
    db.commit()
    return redirect(url_for("inicio", estado=request.form.get("filtro", "Activo")))


@app.post("/asignaciones/<int:asignacion_id>/eliminar")
def eliminar_asignacion(asignacion_id):
    db = get_db()
    db.execute("DELETE FROM asignaciones WHERE id = ?", (asignacion_id,))
    db.commit()
    return redirect(url_for("inicio"))


# --------------------------------------------------------------------------
# API para integraciones (n8n)
# --------------------------------------------------------------------------


@app.get("/health")
def health():
    get_db().execute("SELECT 1")
    return {"ok": True}, 200


def token_valido():
    if not API_TOKEN:
        return False
    enviado = request.headers.get("X-API-Token", "")
    if not enviado:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            enviado = auth[7:]
    return enviado == API_TOKEN


def buscar_o_crear(tabla, nombre, extra_col=None, extra_val=None):
    db = get_db()
    fila = db.execute(f"SELECT id FROM {tabla} WHERE nombre = ?", (nombre,)).fetchone()
    if fila:
        return fila["id"]
    if extra_col:
        cur = db.execute(
            f"INSERT INTO {tabla} (nombre, {extra_col}) VALUES (?, ?)", (nombre, extra_val)
        )
    else:
        cur = db.execute(f"INSERT INTO {tabla} (nombre) VALUES (?)", (nombre,))
    return cur.lastrowid


@app.post("/api/asignaciones")
def api_crear_asignacion():
    """Crea una asignación desde n8n. El técnico y el proyecto se crean si no existen.

    Body JSON:
      {"tecnico": "Juan Pérez", "proyecto": "Planta Norte",
       "rol": "Instalación", "fecha_inicio": "2026-09-16",
       "especialidad": "Eléctrico", "cliente": "ACME"}
    """
    if not token_valido():
        return jsonify(error="Token inválido o ausente"), 401

    datos = request.get_json(silent=True) or {}
    tecnico = (datos.get("tecnico") or "").strip()
    proyecto = (datos.get("proyecto") or "").strip()
    if not tecnico or not proyecto:
        return jsonify(error="Se requieren los campos 'tecnico' y 'proyecto'"), 400

    estado = datos.get("estado", "Activo")
    if estado not in ESTADOS:
        return jsonify(error=f"Estado inválido. Usa uno de: {', '.join(ESTADOS)}"), 400

    db = get_db()
    tecnico_id = buscar_o_crear("tecnicos", tecnico, "especialidad", datos.get("especialidad"))
    proyecto_id = buscar_o_crear("proyectos", proyecto, "cliente", datos.get("cliente"))

    cur = db.execute(
        """INSERT INTO asignaciones (tecnico_id, proyecto_id, rol, fecha_inicio, estado)
           VALUES (?, ?, ?, ?, ?)""",
        (
            tecnico_id,
            proyecto_id,
            (datos.get("rol") or "").strip(),
            datos.get("fecha_inicio") or date.today().isoformat(),
            estado,
        ),
    )
    db.commit()
    return jsonify(id=cur.lastrowid, tecnico=tecnico, proyecto=proyecto, estado=estado), 201


@app.get("/api/asignaciones")
def api_listar_asignaciones():
    if not token_valido():
        return jsonify(error="Token inválido o ausente"), 401

    sql = """
        SELECT a.id, a.rol, a.fecha_inicio, a.fecha_fin, a.estado,
               t.nombre AS tecnico, p.nombre AS proyecto, p.cliente
        FROM asignaciones a
        JOIN tecnicos t ON t.id = a.tecnico_id
        JOIN proyectos p ON p.id = a.proyecto_id
    """
    params = []
    estado = request.args.get("estado")
    if estado in ESTADOS:
        sql += " WHERE a.estado = ?"
        params.append(estado)
    sql += " ORDER BY a.id DESC"

    filas = get_db().execute(sql, params).fetchall()
    return jsonify([dict(f) for f in filas])


@app.patch("/api/asignaciones/<int:asignacion_id>")
def api_actualizar_estado(asignacion_id):
    if not token_valido():
        return jsonify(error="Token inválido o ausente"), 401

    datos = request.get_json(silent=True) or {}
    estado = datos.get("estado")
    if estado not in ESTADOS:
        return jsonify(error=f"Estado inválido. Usa uno de: {', '.join(ESTADOS)}"), 400

    db = get_db()
    fecha_fin = date.today().isoformat() if estado == "Finalizado" else None
    cur = db.execute(
        "UPDATE asignaciones SET estado = ?, fecha_fin = ? WHERE id = ?",
        (estado, fecha_fin, asignacion_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="No existe esa asignación"), 404
    return jsonify(id=asignacion_id, estado=estado)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
