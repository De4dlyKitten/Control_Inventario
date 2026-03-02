# Control de Inventario de Servidores

MVP web sencillo con Flask + SQLite para registrar servidores fisicos y virtuales.

## Requisitos

- Python 3.10+

## Ejecutar

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Luego abre:

`http://127.0.0.1:5000`

## Login

- Usuario: `servidores`
- Clave: `nuevo911`

## Datos que guarda

- Nombre del servidor
- Descripcion de uso
- Marca
- Modelo
- CPU
- RAM (GB)
- IP
- Tipo (`FISICO` o `VIRTUAL`)
- Si es `FISICO`: `rack` y `U`
- Si es `VIRTUAL`: `host fisico`

## Reglas validadas

- `FISICO` requiere rack y U, y no puede tener host fisico.
- `VIRTUAL` requiere host fisico, y no puede tener rack/U.
- Nombre e IP no se pueden repetir.
- `CPU` y `RAM` son opcionales.
- `U` acepta formatos como `38` o `38-39`.
- Sistema operativo limitado a `Windows Server` o `Ubuntu Server`.
- Si el tipo es `VIRTUAL`, la marca se fija automaticamente en `Hyper-V`.
- Para servidores fisicos, `modelo` sigue siendo obligatorio.

## Filtros

El listado permite filtrar por:

- Nombre
- Uso
- Marca
- Modelo
- CPU
- RAM
- IP
- Tipo
- Rack
- U
- Host fisico

## Gestion del listado

- Edicion de servidores desde el boton `Editar`.
- Eliminacion de servidores desde el boton `Eliminar`.
- Paginacion automatica (50 registros por pagina).
- Exportacion de resultados filtrados a CSV (`Exportar CSV`).
