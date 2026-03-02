import csv
import io
import math
import sqlite3
import re
from pathlib import Path
from typing import Any

from flask import Flask, Response, flash, g, jsonify, redirect, render_template, request, session, url_for


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "inventory.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-me"
PER_PAGE = 25
OS_OPTIONS = {"Windows Server", "Ubuntu Server"}
ADMIN_USERNAME = "servidores"
ADMIN_PASSWORD = "nuevo911"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def is_authenticated() -> bool:
    return session.get("auth_user") == ADMIN_USERNAME


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.before_request
def require_login():
    allowed_endpoints = {"login", "static"}
    endpoint = request.endpoint
    if endpoint is None or endpoint in allowed_endpoints:
        return None
    if is_authenticated():
        return None
    return redirect(url_for("login", next=request.full_path.rstrip("?")))


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_servidor TEXT NOT NULL UNIQUE,
            descripcion_uso TEXT NOT NULL,
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            cpu TEXT,
            ram_gb INTEGER CHECK (ram_gb > 0),
            ip TEXT,
            tipo TEXT NOT NULL CHECK (tipo IN ('FISICO', 'VIRTUAL')),
            sistema_operativo TEXT,
            numero_serial TEXT,
            numero_activo_fijo TEXT,
            rack TEXT,
            unidad_u TEXT,
            host_fisico_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (host_fisico_id) REFERENCES servers(id)
        );
        """
    )
    migrate_servers_table_if_needed(db)
    ensure_operating_system_column(db)
    ensure_physical_asset_columns(db)
    ensure_ip_nullable_not_unique(db)
    db.commit()


def migrate_servers_table_if_needed(db: sqlite3.Connection) -> None:
    columns = db.execute("PRAGMA table_info(servers)").fetchall()
    if not columns:
        return

    column_map = {row["name"]: row for row in columns}
    needs_migration = False

    cpu_info = column_map.get("cpu")
    ram_info = column_map.get("ram_gb")
    unidad_u_info = column_map.get("unidad_u")

    cpu_notnull = bool(cpu_info and cpu_info["notnull"] == 1)
    ram_notnull = bool(ram_info and ram_info["notnull"] == 1)
    unidad_u_type = str(unidad_u_info["type"]).upper() if unidad_u_info else ""

    if cpu_notnull or ram_notnull or "INT" in unidad_u_type:
        needs_migration = True

    if not needs_migration:
        return

    db.executescript(
        """
        CREATE TABLE servers_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_servidor TEXT NOT NULL UNIQUE,
            descripcion_uso TEXT NOT NULL,
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            cpu TEXT,
            ram_gb INTEGER CHECK (ram_gb > 0),
            ip TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL CHECK (tipo IN ('FISICO', 'VIRTUAL')),
            sistema_operativo TEXT,
            numero_serial TEXT,
            numero_activo_fijo TEXT,
            rack TEXT,
            unidad_u TEXT,
            host_fisico_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (host_fisico_id) REFERENCES servers_new(id)
        );

        INSERT INTO servers_new (
            id,
            nombre_servidor,
            descripcion_uso,
            marca,
            modelo,
            cpu,
            ram_gb,
            ip,
            tipo,
            sistema_operativo,
            numero_serial,
            numero_activo_fijo,
            rack,
            unidad_u,
            host_fisico_id,
            created_at
        )
        SELECT
            id,
            nombre_servidor,
            descripcion_uso,
            marca,
            modelo,
            cpu,
            ram_gb,
            ip,
            tipo,
            NULL,
            NULL,
            NULL,
            rack,
            CAST(unidad_u AS TEXT),
            host_fisico_id,
            created_at
        FROM servers;

        DROP TABLE servers;
        ALTER TABLE servers_new RENAME TO servers;
        """
    )


def ensure_operating_system_column(db: sqlite3.Connection) -> None:
    columns = db.execute("PRAGMA table_info(servers)").fetchall()
    names = {row["name"] for row in columns}
    if "sistema_operativo" not in names:
        db.execute("ALTER TABLE servers ADD COLUMN sistema_operativo TEXT")


def ensure_physical_asset_columns(db: sqlite3.Connection) -> None:
    columns = db.execute("PRAGMA table_info(servers)").fetchall()
    names = {row["name"] for row in columns}
    if "numero_serial" not in names:
        db.execute("ALTER TABLE servers ADD COLUMN numero_serial TEXT")
    if "numero_activo_fijo" not in names:
        db.execute("ALTER TABLE servers ADD COLUMN numero_activo_fijo TEXT")


def ensure_ip_nullable_not_unique(db: sqlite3.Connection) -> None:
    columns = db.execute("PRAGMA table_info(servers)").fetchall()
    names = {row["name"] for row in columns}
    if "ip" not in names:
        return

    ip_info = next((row for row in columns if row["name"] == "ip"), None)
    ip_notnull = bool(ip_info and ip_info["notnull"] == 1)

    has_unique_ip_index = False
    indexes = db.execute("PRAGMA index_list(servers)").fetchall()
    for idx in indexes:
        if idx["unique"] != 1:
            continue
        idx_name = idx["name"]
        idx_cols = db.execute(f"PRAGMA index_info('{idx_name}')").fetchall()
        col_names = [c["name"] for c in idx_cols]
        if col_names == ["ip"]:
            has_unique_ip_index = True
            break

    if not ip_notnull and not has_unique_ip_index:
        return

    db.executescript(
        """
        CREATE TABLE servers_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_servidor TEXT NOT NULL UNIQUE,
            descripcion_uso TEXT NOT NULL,
            marca TEXT NOT NULL,
            modelo TEXT NOT NULL,
            cpu TEXT,
            ram_gb INTEGER CHECK (ram_gb > 0),
            ip TEXT,
            tipo TEXT NOT NULL CHECK (tipo IN ('FISICO', 'VIRTUAL')),
            sistema_operativo TEXT,
            numero_serial TEXT,
            numero_activo_fijo TEXT,
            rack TEXT,
            unidad_u TEXT,
            host_fisico_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (host_fisico_id) REFERENCES servers_new(id)
        );

        INSERT INTO servers_new (
            id,
            nombre_servidor,
            descripcion_uso,
            marca,
            modelo,
            cpu,
            ram_gb,
            ip,
            tipo,
            sistema_operativo,
            numero_serial,
            numero_activo_fijo,
            rack,
            unidad_u,
            host_fisico_id,
            created_at
        )
        SELECT
            id,
            nombre_servidor,
            descripcion_uso,
            marca,
            modelo,
            cpu,
            ram_gb,
            NULLIF(ip, ''),
            tipo,
            sistema_operativo,
            numero_serial,
            numero_activo_fijo,
            rack,
            unidad_u,
            host_fisico_id,
            created_at
        FROM servers;

        DROP TABLE servers;
        ALTER TABLE servers_new RENAME TO servers;
        """
    )


FILTER_MAP = {
    "nombre_servidor": "s.nombre_servidor",
    "descripcion_uso": "s.descripcion_uso",
    "marca": "s.marca",
    "modelo": "s.modelo",
    "cpu": "s.cpu",
    "ram_gb": "CAST(s.ram_gb AS TEXT)",
    "ip": "s.ip",
    "sistema_operativo": "s.sistema_operativo",
    "rack": "s.rack",
    "unidad_u": "s.unidad_u",
    "host_fisico_nombre": "h.nombre_servidor",
}


def build_filter_conditions(filters: dict[str, str]) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    for key, column in FILTER_MAP.items():
        value = filters.get(key, "")
        if value:
            conditions.append(f"LOWER(COALESCE({column}, '')) LIKE ?")
            params.append(f"%{value.lower()}%")

    tipo = filters.get("tipo", "")
    if tipo:
        conditions.append("s.tipo = ?")
        params.append(tipo)

    if not conditions:
        return "", params

    return " WHERE " + " AND ".join(conditions), params


def fetch_servers(
    filters: dict[str, str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[sqlite3.Row]:
    db = get_db()
    filters = filters or {}
    query = """
        SELECT
            s.id,
            s.nombre_servidor,
            s.descripcion_uso,
            s.marca,
            s.modelo,
            s.cpu,
            s.ram_gb,
            s.ip,
            s.tipo,
            s.sistema_operativo,
            s.numero_serial,
            s.numero_activo_fijo,
            s.rack,
            s.unidad_u,
            s.host_fisico_id,
            h.nombre_servidor AS host_fisico_nombre,
            s.created_at
        FROM servers AS s
        LEFT JOIN servers AS h ON h.id = s.host_fisico_id
    """
    where_sql, params = build_filter_conditions(filters)
    query += where_sql

    query += " ORDER BY s.id DESC"
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    return list(rows)


def fetch_physical_servers() -> list[sqlite3.Row]:
    db = get_db()
    rows = db.execute(
        "SELECT id, nombre_servidor FROM servers WHERE tipo = 'FISICO' ORDER BY nombre_servidor ASC"
    ).fetchall()
    return list(rows)


def count_servers(filters: dict[str, str]) -> int:
    db = get_db()
    query = """
        SELECT COUNT(*)
        FROM servers AS s
        LEFT JOIN servers AS h ON h.id = s.host_fisico_id
    """
    where_sql, params = build_filter_conditions(filters)
    query += where_sql
    return int(db.execute(query, params).fetchone()[0])


def get_server_by_id(server_id: int) -> sqlite3.Row | None:
    db = get_db()
    return db.execute(
        """
        SELECT
            id,
            nombre_servidor,
            descripcion_uso,
            marca,
            modelo,
            cpu,
            ram_gb,
            ip,
            tipo,
            sistema_operativo,
            numero_serial,
            numero_activo_fijo,
            rack,
            unidad_u,
            host_fisico_id
        FROM servers
        WHERE id = ?
        """,
        (server_id,),
    ).fetchone()


def get_server_summary_by_id(server_id: int) -> sqlite3.Row | None:
    db = get_db()
    return db.execute(
        """
        SELECT
            s.id,
            s.nombre_servidor,
            s.descripcion_uso,
            s.marca,
            s.modelo,
            s.cpu,
            s.ram_gb,
            s.ip,
            s.tipo,
            s.sistema_operativo,
            s.numero_serial,
            s.numero_activo_fijo,
            s.rack,
            s.unidad_u,
            h.nombre_servidor AS host_fisico_nombre,
            s.created_at
        FROM servers AS s
        LEFT JOIN servers AS h ON h.id = s.host_fisico_id
        WHERE s.id = ?
        """,
        (server_id,),
    ).fetchone()


def get_next_available_server_id() -> int:
    db = get_db()
    row = db.execute(
        """
        SELECT
            CASE
                WHEN NOT EXISTS (SELECT 1 FROM servers WHERE id = 1) THEN 1
                ELSE (
                    SELECT MIN(s1.id) + 1
                    FROM servers AS s1
                    WHERE NOT EXISTS (
                        SELECT 1 FROM servers AS s2 WHERE s2.id = s1.id + 1
                    )
                )
            END AS next_id
        """
    ).fetchone()
    return int(row["next_id"])


def normalize_text(value: str) -> str:
    return value.strip()


def validate_payload(form_data: dict[str, str]) -> list[str]:
    errors: list[str] = []

    tipo = form_data["tipo"]
    rack = form_data["rack"]
    unidad_u = form_data["unidad_u"]
    numero_serial = form_data["numero_serial"]
    numero_activo_fijo = form_data["numero_activo_fijo"]
    host_fisico_id = form_data["host_fisico_id"]

    if tipo == "FISICO":
        if not rack:
            errors.append("Para un servidor fisico, el rack es obligatorio.")
        if not unidad_u:
            errors.append("Para un servidor fisico, la U es obligatoria.")
        if not numero_serial:
            errors.append("Para un servidor fisico, el numero de serial es obligatorio.")
        if not numero_activo_fijo:
            errors.append("Para un servidor fisico, el numero de activo fijo es obligatorio.")
        if host_fisico_id:
            errors.append("Un servidor fisico no puede tener host fisico asignado.")

    if tipo == "VIRTUAL":
        if rack or unidad_u:
            errors.append("Un servidor virtual no debe tener rack ni U.")
        if numero_serial or numero_activo_fijo:
            errors.append("Un servidor virtual no debe tener serial ni activo fijo.")
        if not host_fisico_id:
            errors.append("Para un servidor virtual, debes seleccionar un host fisico.")

    return errors


def is_valid_u_format(unidad_u: str) -> bool:
    if not unidad_u:
        return False
    if not re.fullmatch(r"\d+(?:-\d+)?", unidad_u):
        return False
    if "-" not in unidad_u:
        return True
    start, end = unidad_u.split("-", maxsplit=1)
    return int(start) < int(end)


def get_form_data() -> dict[str, str]:
    return {
        "nombre_servidor": normalize_text(request.form.get("nombre_servidor", "")),
        "descripcion_uso": normalize_text(request.form.get("descripcion_uso", "")),
        "marca": normalize_text(request.form.get("marca", "")),
        "modelo": normalize_text(request.form.get("modelo", "")),
        "cpu": normalize_text(request.form.get("cpu", "")),
        "ram_gb": normalize_text(request.form.get("ram_gb", "")),
        "ip": normalize_text(request.form.get("ip", "")),
        "tipo": normalize_text(request.form.get("tipo", "")),
        "sistema_operativo": normalize_text(request.form.get("sistema_operativo", "")),
        "numero_serial": normalize_text(request.form.get("numero_serial", "")),
        "numero_activo_fijo": normalize_text(request.form.get("numero_activo_fijo", "")),
        "rack": normalize_text(request.form.get("rack", "")),
        "unidad_u": normalize_text(request.form.get("unidad_u", "")),
        "host_fisico_id": normalize_text(request.form.get("host_fisico_id", "")),
    }


def get_filters() -> dict[str, str]:
    return {
        "nombre_servidor": normalize_text(request.args.get("nombre_servidor", "")),
        "descripcion_uso": normalize_text(request.args.get("descripcion_uso", "")),
        "marca": normalize_text(request.args.get("marca", "")),
        "modelo": normalize_text(request.args.get("modelo", "")),
        "cpu": normalize_text(request.args.get("cpu", "")),
        "ram_gb": normalize_text(request.args.get("ram_gb", "")),
        "ip": normalize_text(request.args.get("ip", "")),
        "tipo": normalize_text(request.args.get("tipo", "")),
        "sistema_operativo": normalize_text(request.args.get("sistema_operativo", "")),
        "rack": normalize_text(request.args.get("rack", "")),
        "unidad_u": normalize_text(request.args.get("unidad_u", "")),
        "host_fisico_nombre": normalize_text(request.args.get("host_fisico_nombre", "")),
    }


def parse_page(raw_page: str | None) -> int:
    if not raw_page or not raw_page.isdigit():
        return 1
    return max(1, int(raw_page))


def resolve_next_url(next_url: str | None) -> str:
    if next_url and next_url.startswith("/"):
        return next_url
    return url_for("index")


@app.route("/login", methods=["GET", "POST"])
def login():
    if is_authenticated():
        return redirect(url_for("index"))

    if request.method == "POST":
        username = normalize_text(request.form.get("username", ""))
        password = request.form.get("password", "")
        next_url = resolve_next_url(request.form.get("next"))
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["auth_user"] = ADMIN_USERNAME
            flash("Sesion iniciada correctamente.", "success")
            return redirect(next_url)
        flash("Credenciales invalidas.", "error")

    next_url = resolve_next_url(request.values.get("next"))
    return render_template("login.html", next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


def validate_server_form(form_data: dict[str, str], current_server_id: int | None = None) -> list[str]:
    required_fields = ["nombre_servidor", "descripcion_uso", "marca", "tipo", "sistema_operativo"]
    missing = [field for field in required_fields if not form_data[field]]
    errors: list[str] = []

    if missing:
        errors.append("Completa todos los campos obligatorios.")

    if form_data["tipo"] not in {"FISICO", "VIRTUAL"}:
        errors.append("Tipo invalido: usa FISICO o VIRTUAL.")

    if form_data["sistema_operativo"] not in OS_OPTIONS:
        errors.append("Sistema operativo invalido: usa Windows Server o Ubuntu Server.")

    if form_data["tipo"] == "FISICO" and not form_data["modelo"]:
        errors.append("Para un servidor fisico, el modelo es obligatorio.")

    if form_data["ram_gb"] and not form_data["ram_gb"].isdigit():
        errors.append("RAM debe ser un numero entero en GB.")

    if form_data["unidad_u"] and not is_valid_u_format(form_data["unidad_u"]):
        errors.append("La U debe tener formato valido: '38' o '38-39'.")

    errors.extend(validate_payload(form_data))

    db = get_db()
    if form_data["host_fisico_id"]:
        if not form_data["host_fisico_id"].isdigit():
            errors.append("Host fisico invalido.")
            return errors
        host_id = int(form_data["host_fisico_id"])
        if current_server_id is not None and host_id == current_server_id:
            errors.append("Un servidor no puede ser host de si mismo.")
        host = db.execute("SELECT id, tipo FROM servers WHERE id = ?", (host_id,)).fetchone()
        if host is None:
            errors.append("El host fisico seleccionado no existe.")
        elif host["tipo"] != "FISICO":
            errors.append("El host asignado debe ser de tipo FISICO.")

    return errors


def apply_business_defaults(form_data: dict[str, str]) -> None:
    if form_data["tipo"] == "VIRTUAL":
        form_data["marca"] = "Hyper-V"
        form_data["numero_serial"] = ""
        form_data["numero_activo_fijo"] = ""


@app.route("/", methods=["GET", "POST"])
def index():
    init_db()
    show_add_form = False

    if request.method == "POST":
        show_add_form = True
        form_data = get_form_data()
        apply_business_defaults(form_data)
        errors = validate_server_form(form_data)

        if not errors:
            db = get_db()
            try:
                db.execute(
                    """
                    INSERT INTO servers (
                        id,
                        nombre_servidor,
                        descripcion_uso,
                        marca,
                        modelo,
                        cpu,
                        ram_gb,
                        ip,
                        tipo,
                        sistema_operativo,
                        numero_serial,
                        numero_activo_fijo,
                        rack,
                        unidad_u,
                        host_fisico_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        get_next_available_server_id(),
                        form_data["nombre_servidor"],
                        form_data["descripcion_uso"],
                        form_data["marca"],
                        form_data["modelo"],
                        form_data["cpu"] or None,
                        int(form_data["ram_gb"]) if form_data["ram_gb"] else None,
                        form_data["ip"] or None,
                        form_data["tipo"],
                        form_data["sistema_operativo"],
                        form_data["numero_serial"] or None,
                        form_data["numero_activo_fijo"] or None,
                        form_data["rack"] or None,
                        form_data["unidad_u"] or None,
                        int(form_data["host_fisico_id"]) if form_data["host_fisico_id"] else None,
                    ),
                )
                db.commit()
                flash("Servidor guardado correctamente.", "success")
                return redirect(url_for("index"))
            except sqlite3.IntegrityError as exc:
                message = str(exc).lower()
                if "nombre_servidor" in message:
                    errors.append("Ya existe un servidor con ese nombre.")
                elif "ip" in message:
                    errors.append("La IP ya existe en el inventario.")
                else:
                    errors.append("No se pudo guardar por una restriccion de datos.")

        for error in errors:
            flash(error, "error")

    filters = get_filters()
    page = parse_page(request.args.get("page"))
    total_results = count_servers(filters)
    total_pages = max(1, math.ceil(total_results / PER_PAGE)) if total_results else 1
    if page > total_pages:
        page = total_pages
    servers = fetch_servers(filters, limit=PER_PAGE, offset=(page - 1) * PER_PAGE)
    physical_servers = fetch_physical_servers()
    active_filters = {key: value for key, value in filters.items() if value}
    page_urls = [(n, url_for("index", page=n, **active_filters)) for n in range(1, total_pages + 1)]
    prev_url = url_for("index", page=page - 1, **active_filters) if page > 1 else None
    next_url = url_for("index", page=page + 1, **active_filters) if page < total_pages else None
    current_url = request.full_path.rstrip("?")
    return render_template(
        "index.html",
        servers=servers,
        physical_servers=physical_servers,
        show_add_form=show_add_form,
        filters=filters,
        active_filters=active_filters,
        total_results=total_results,
        page=page,
        total_pages=total_pages,
        page_urls=page_urls,
        prev_url=prev_url,
        next_url=next_url,
        current_url=current_url,
    )


@app.route("/servers/<int:server_id>/edit", methods=["GET", "POST"])
def edit_server(server_id: int):
    init_db()
    server = get_server_by_id(server_id)
    if server is None:
        flash("El servidor no existe.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        form_data = get_form_data()
        apply_business_defaults(form_data)
        errors = validate_server_form(form_data, current_server_id=server_id)
        next_url = resolve_next_url(request.form.get("next"))

        if not errors:
            db = get_db()
            try:
                db.execute(
                    """
                    UPDATE servers
                    SET
                        nombre_servidor = ?,
                        descripcion_uso = ?,
                        marca = ?,
                        modelo = ?,
                        cpu = ?,
                        ram_gb = ?,
                        ip = ?,
                        tipo = ?,
                        sistema_operativo = ?,
                        numero_serial = ?,
                        numero_activo_fijo = ?,
                        rack = ?,
                        unidad_u = ?,
                        host_fisico_id = ?
                    WHERE id = ?
                    """,
                    (
                        form_data["nombre_servidor"],
                        form_data["descripcion_uso"],
                        form_data["marca"],
                        form_data["modelo"],
                        form_data["cpu"] or None,
                        int(form_data["ram_gb"]) if form_data["ram_gb"] else None,
                        form_data["ip"] or None,
                        form_data["tipo"],
                        form_data["sistema_operativo"],
                        form_data["numero_serial"] or None,
                        form_data["numero_activo_fijo"] or None,
                        form_data["rack"] or None,
                        form_data["unidad_u"] or None,
                        int(form_data["host_fisico_id"]) if form_data["host_fisico_id"] else None,
                        server_id,
                    ),
                )
                db.commit()
                flash("Servidor actualizado correctamente.", "success")
                return redirect(next_url)
            except sqlite3.IntegrityError as exc:
                message = str(exc).lower()
                if "nombre_servidor" in message:
                    errors.append("Ya existe un servidor con ese nombre.")
                elif "ip" in message:
                    errors.append("La IP ya existe en el inventario.")
                else:
                    errors.append("No se pudo actualizar por una restriccion de datos.")

        for error in errors:
            flash(error, "error")

    safe_next = resolve_next_url(request.values.get("next"))
    server = get_server_by_id(server_id)
    physical_servers = fetch_physical_servers()
    return render_template(
        "edit.html",
        server=server,
        physical_servers=physical_servers,
        next_url=safe_next,
    )


@app.route("/servers/<int:server_id>/delete", methods=["POST"])
def delete_server(server_id: int):
    init_db()
    db = get_db()
    next_url = resolve_next_url(request.form.get("next"))
    try:
        result = db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        db.commit()
        if result.rowcount == 0:
            flash("El servidor no existe.", "error")
        else:
            flash("Servidor eliminado correctamente.", "success")
    except sqlite3.IntegrityError:
        flash("No se puede eliminar: hay servidores virtuales asociados a este host fisico.", "error")

    return redirect(next_url)


@app.route("/export.csv", methods=["GET"])
def export_csv():
    init_db()
    filters = get_filters()
    servers = fetch_servers(filters)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Nombre",
            "Uso",
            "Marca",
            "Modelo",
            "CPU",
            "RAM_GB",
            "IP",
            "Tipo",
            "Sistema_Operativo",
            "Numero_Serial",
            "Numero_Activo_Fijo",
            "Rack",
            "U",
            "Host_Fisico",
            "Creado_En",
        ]
    )
    for server in servers:
        writer.writerow(
            [
                server["id"],
                server["nombre_servidor"],
                server["descripcion_uso"],
                server["marca"],
                server["modelo"],
                server["cpu"] or "",
                server["ram_gb"] or "",
                server["ip"],
                server["tipo"],
                server["sistema_operativo"] or "",
                server["numero_serial"] or "",
                server["numero_activo_fijo"] or "",
                server["rack"] or "",
                server["unidad_u"] or "",
                server["host_fisico_nombre"] or "",
                server["created_at"],
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=inventario_servidores.csv"},
    )


@app.route("/servers/<int:server_id>/summary", methods=["GET"])
def server_summary(server_id: int):
    init_db()
    server = get_server_summary_by_id(server_id)
    if server is None:
        return jsonify({"error": "Servidor no encontrado"}), 404

    payload = {
        "id": server["id"],
        "nombre_servidor": server["nombre_servidor"],
        "descripcion_uso": server["descripcion_uso"],
        "marca": server["marca"],
        "modelo": server["modelo"],
        "cpu": server["cpu"],
        "ram_gb": server["ram_gb"],
        "ip": server["ip"],
        "tipo": server["tipo"],
        "sistema_operativo": server["sistema_operativo"],
        "numero_serial": server["numero_serial"],
        "numero_activo_fijo": server["numero_activo_fijo"],
        "rack": server["rack"],
        "unidad_u": server["unidad_u"],
        "host_fisico_nombre": server["host_fisico_nombre"],
        "created_at": server["created_at"],
    }
    return jsonify(payload)


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)
