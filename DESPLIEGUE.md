# Despliegue en Coolify + integración con n8n

## 1. Crear el recurso en Coolify

Dos caminos, elige uno.

**A. Desde el repositorio (recomendado)**
Sube esta carpeta a un repo Git y en Coolify:
`+ New` → `Application` → tu repositorio → Build Pack: **Dockerfile**.

**B. Desde una imagen ya construida**
Construye y publica la imagen:

    docker build -t tu-registry/registro-tecnicos:1.0 .
    docker push tu-registry/registro-tecnicos:1.0

En Coolify: `+ New` → `Docker Image` → `tu-registry/registro-tecnicos:1.0`.

## 2. Acceso por IP y puerto (sin dominio)

Esta es la parte que suele fallar. Coolify por defecto genera un dominio y
enruta por su proxy; para acceso local por IP hay que hacer dos cosas:

1. En la pestaña **General** del recurso, **borra el dominio autogenerado**
   (campo `Domains`). Si lo dejas, el tráfico solo entra por el proxy.
2. En **Ports Mappings** pon `8000:8000` (host:contenedor). Puedes usar otro
   puerto del host si el 8000 está ocupado por Coolify mismo: `8090:8000`.
3. `Ports Exposes` debe decir `8000` (el puerto interno del contenedor).

Con eso entras en `http://IP-DEL-SERVIDOR:8090`.

> Nota: Coolify suele ocupar el 8000 del host. Si es tu caso, mapea a 8090 o
> similar para evitar el choque.

## 3. Datos persistentes

En **Storages** del recurso, agrega un volumen:

- Name: `registro-datos`
- Mount Path: `/data`

Sin esto, la base SQLite se pierde en cada redeploy.

## 4. Variables de entorno

En **Environment Variables**:

| Variable    | Valor                        |
|-------------|------------------------------|
| `DB_PATH`   | `/data/registro.db`          |
| `PORT`      | `8000`                       |
| `API_TOKEN` | un token largo y aleatorio   |

Genera el token con: `openssl rand -hex 32`

Sin `API_TOKEN`, la API queda cerrada (devuelve 401 siempre). La interfaz web
sigue funcionando.

## 5. Enviar datos desde n8n

### Crear una asignación

Nodo **HTTP Request**:

- Method: `POST`
- URL: `http://IP-DEL-SERVIDOR:8090/api/asignaciones`
- Headers: `X-API-Token` = tu token
- Body Content Type: `JSON`

```json
{
  "tecnico": "Juan Pérez",
  "proyecto": "Planta Norte",
  "rol": "Instalación",
  "fecha_inicio": "2026-09-16",
  "especialidad": "Eléctrico",
  "cliente": "ACME"
}
```

Solo `tecnico` y `proyecto` son obligatorios. Si no existen, se crean solos.
Respuesta `201` con el `id` de la asignación.

### Consultar asignaciones

`GET /api/asignaciones` — opcional `?estado=Activo`
Header: `X-API-Token`

### Cambiar estado

`PATCH /api/asignaciones/12` con body `{"estado": "Finalizado"}`
Al finalizar se guarda la fecha de cierre automáticamente.

### Si n8n está en el mismo servidor Coolify

Puedes evitar salir a la red: conecta ambos recursos a la misma red Docker
(en Coolify, campo `Connect To Predefined Network` o añadiendo la red en
**Network** del recurso) y usa el nombre del contenedor como host:

    http://registro-tecnicos:8000/api/asignaciones

Es más rápido y no depende de la IP del host.

## 6. Probar

    curl http://IP-DEL-SERVIDOR:8090/health
    # {"ok": true}

    curl -X POST http://IP-DEL-SERVIDOR:8090/api/asignaciones \
      -H "X-API-Token: TU_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"tecnico":"Ana Torres","proyecto":"Bodega Sur","rol":"Redes"}'
