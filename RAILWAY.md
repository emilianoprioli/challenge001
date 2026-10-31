# Deploy en Railway

## 1. Crear el proyecto

1. Crear un proyecto en Railway.
2. Agregar un servicio PostgreSQL llamado `Postgres`.
3. Crear el servicio API desde el repositorio.
4. Dejar Root Directory vacío o `/`, porque este repositorio Git comienza
   directamente en el workspace del microservicio.

Railway detectará el `Dockerfile` en la raíz del repositorio.

## 2. Variables del servicio API

En Variables → Raw Editor, pegar el contenido de `.env.railway.example`.

La referencia:

```text
COMPUTE_DATABASE_URL=${{Postgres.DATABASE_URL}}
```

utiliza la red privada entre el servicio API y PostgreSQL. No es necesario exponer
la base públicamente.

Railway inyecta automáticamente `PORT`; el container ya está configurado para
escucharlo.

## 3. Migraciones

En Settings → Deploy → Pre-Deploy Command configurar:

```text
alembic upgrade head
```

Configurar un timeout de 300 segundos. Si la migración falla, el deploy no debe
continuar.

## 4. Health check

En Settings → Deploy → Healthcheck Path configurar:

```text
/health/live
```

## 5. Dominio público

En Settings → Networking generar un dominio público para el servicio API. La base
de datos debe permanecer privada.

## 6. Verificación inicial

```text
GET https://<dominio>/health/live
```

Debe responder:

```json
{"status":"ok"}
```

Las pruebas de carga se agregarán después de implementar los endpoints de negocio.
Se ejecutarán de forma gradual, con límites de concurrencia y presupuesto para no
generar costos inesperados.
