# Guia de Despliegue Empresarial - Control de Inventario

Fecha: 2026-02-23

## 1) Arquitectura recomendada

### Opcion recomendada (produccion)
- Hyper-V Host
- VM Ubuntu Server 24.04 LTS
- Nginx (reverse proxy)
- Gunicorn (servidor WSGI para Flask)
- PostgreSQL 16 (base de datos)
- DNS interno (Windows DNS)
- Certificado TLS (CA interna o publico)

### Opcion rapida (piloto / laboratorio)
- Igual que arriba, pero usando SQLite temporalmente.
- Solo recomendada para pilotos o baja concurrencia.

## 2) Requisitos de infraestructura

- 1 VM (produccion minima):
- 2 vCPU
- 8 GB RAM
- 80 GB disco
- IP fija (ejemplo: 10.20.30.50)
- Acceso desde red LAN a puertos 80 y 443
- DNS interno administrado (Active Directory DNS recomendado)

## 3) Paso a paso en Hyper-V

1. Crear VM Generacion 2.
2. Asignar 2 vCPU, 8 GB RAM, disco 80 GB.
3. Conectar a vSwitch externo para red LAN.
4. Instalar Ubuntu Server 24.04 LTS.
5. Configurar IP fija en la VM.
6. Actualizar sistema:

```bash
sudo apt update && sudo apt -y upgrade
```

## 4) Preparar aplicacion en Ubuntu

1. Instalar paquetes base:

```bash
sudo apt install -y python3-venv python3-pip nginx git
```

2. Crear ruta de aplicacion:

```bash
sudo mkdir -p /opt/control_inventario
sudo chown $USER:$USER /opt/control_inventario
```

3. Copiar proyecto a `/opt/control_inventario`.

4. Crear entorno virtual e instalar dependencias:

```bash
cd /opt/control_inventario
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

## 5) Crear servicio systemd (Gunicorn)

Crear archivo `/etc/systemd/system/control-inventario.service`:

```ini
[Unit]
Description=Control Inventario Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/control_inventario
Environment="PATH=/opt/control_inventario/.venv/bin"
ExecStart=/opt/control_inventario/.venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Aplicar:

```bash
sudo chown -R www-data:www-data /opt/control_inventario
sudo systemctl daemon-reload
sudo systemctl enable --now control-inventario
sudo systemctl status control-inventario
```

## 6) Configurar Nginx

Crear `/etc/nginx/sites-available/control-inventario`:

```nginx
server {
    listen 80;
    server_name inventario.empresa.local;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Activar:

```bash
sudo ln -s /etc/nginx/sites-available/control-inventario /etc/nginx/sites-enabled/control-inventario
sudo nginx -t
sudo systemctl reload nginx
```

## 7) DNS interno para acceso facil

Objetivo: acceder desde cualquier PC con `http://inventario.empresa.local`.

1. En servidor DNS de AD, abrir DNS Manager.
2. En la zona interna (`empresa.local`), crear registro A:
- Nombre: `inventario`
- IP: `10.20.30.50` (IP fija de la VM)
3. Verificar desde un equipo cliente:

```powershell
nslookup inventario.empresa.local
```

## 8) HTTPS (recomendado)

Opciones:
- CA interna (si es solo red corporativa)
- Certificado publico (si el dominio es publico y resoluble)

Aplicar certificado en Nginx y redirigir HTTP -> HTTPS.

## 9) Base de datos: recomendacion empresarial

Recomendado: migrar de SQLite a PostgreSQL para produccion.

Ventajas:
- Mejor concurrencia
- Backups consistentes
- Mayor control de seguridad y recuperacion

Plan de migracion:
1. Crear instancia PostgreSQL.
2. Definir esquema equivalente.
3. Migrar datos actuales.
4. Cambiar capa de acceso en app (SQLAlchemy o adaptador PostgreSQL).
5. Probar en entorno QA antes de produccion.

## 10) Backups y operacion

- Backup diario de base de datos.
- Backup de `/opt/control_inventario` y archivos de configuracion.
- Monitoreo de servicio:

```bash
sudo systemctl status control-inventario
sudo systemctl status nginx
```

- Logs:

```bash
journalctl -u control-inventario -f
sudo tail -f /var/log/nginx/error.log
```

## 11) Checklist de salida a produccion

- VM con IP fija
- DNS resolviendo desde clientes
- Nginx operativo
- Gunicorn operativo
- HTTPS activo
- Backup probado (restore probado)
- Acceso validado desde al menos 3 equipos de red
- Documentacion de credenciales y responsables

## 12) Recomendacion final de sistema operativo

- VM aplicacion: Ubuntu Server 24.04 LTS (estabilidad, soporte largo, despliegue simple).
- DNS corporativo: Windows Server DNS (si ya usan Active Directory).
- Base de datos: PostgreSQL 16 en Linux (dedicada o compartida segun capacidad).

## Referencias oficiales

- Ubuntu 24.04 LTS release notes: https://discourse.ubuntu.com/t/ubuntu-24-04-lts-noble-numbat-release-notes/39890
- Flask deployment docs: https://flask.palletsprojects.com/en/stable/deploying/
- Gunicorn docs: https://docs.gunicorn.org/en/stable/
- Nginx docs: https://nginx.org/en/docs/
- PostgreSQL docs: https://www.postgresql.org/docs/
- Hyper-V overview (Microsoft): https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/hyper-v-overview
- DNS in Windows Server (Microsoft): https://learn.microsoft.com/en-us/windows-server/networking/dns/
- Add-DnsServerResourceRecordA (Microsoft): https://learn.microsoft.com/en-us/powershell/module/dnsserver/add-dnsserverresourcerecorda
