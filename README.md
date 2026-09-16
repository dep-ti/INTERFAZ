# Registro de técnicos por proyecto

Interfaz web mínima (Flask + SQLite) para registrar en qué proyecto está cada técnico.

## Levantar con Docker Compose

    docker compose up --build

Abrir http://localhost:8000

## Solo con Docker

    docker build -t registro-tecnicos .
    docker run -d -p 8000:8000 -v registro_datos:/data registro-tecnicos

## Notas

- La base de datos vive en `/data/registro.db`, dentro de un volumen, así que los
  datos sobreviven a `docker compose down` (usa `down -v` para borrarlos).
- Las tablas se crean solas al arrancar.
- No hay autenticación: pensada para una red interna.
