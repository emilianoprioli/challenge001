# Arquitectura Railway

Un solo repositorio alimenta tres servicios con comandos de inicio diferentes.

```text
Visualizador local -> HTTPS -> API publica
                                |
                      PostgreSQL privado
                                |
                         Worker privado
                                |
                       Provider privado
```

## Postgres

Crear una base llamada `Postgres`. No necesita dominio publico.

## API

- Source: este repositorio.
- Public Networking: habilitado.
- Pre-deploy command: `alembic upgrade head`.
- Healthcheck: `/health/ready`.
- Start command:

```text
/bin/sh -c "exec uvicorn compute_provisioner.main:app --host 0.0.0.0 --port $PORT"
```

Variables:

```text
COMPUTE_ENVIRONMENT=production
COMPUTE_DATABASE_URL=${{Postgres.DATABASE_URL}}
COMPUTE_DATABASE_POOL_SIZE=5
COMPUTE_DATABASE_MAX_OVERFLOW=5
COMPUTE_DATABASE_POOL_TIMEOUT_SECONDS=10
COMPUTE_CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
COMPUTE_PROVIDER_URL=http://provider.railway.internal:8080
```

## Provider

- Source: el mismo repositorio.
- Public Networking: deshabilitado.
- Variable `PORT=8080` para fijar el puerto privado.
- Start command:

```text
uvicorn compute_provisioner.provider_simulator:app --host 0.0.0.0 --port 8080
```

Variables para que la capacidad sea finita y observable:

```text
COMPUTE_PROVIDER_MAX_CONCURRENCY=5
COMPUTE_PROVIDER_MAX_QUEUE_SIZE=20
COMPUTE_PROVIDER_PROCESSING_MS=250
```

`GET /capacity` permanece en la red privada. La API consulta ese endpoint y publica un
snapshot agregado, sin exponer directamente el proveedor.

## Worker

- Source: el mismo repositorio.
- Public Networking: deshabilitado.
- Sin healthcheck HTTP.
- Start command: `python -m compute_provisioner.worker`.

Variables:

```text
COMPUTE_ENVIRONMENT=production
COMPUTE_DATABASE_URL=${{Postgres.DATABASE_URL}}
COMPUTE_PROVIDER_URL=http://provider.railway.internal:8080
COMPUTE_PROVIDER_TIMEOUT_SECONDS=3
COMPUTE_WORKER_POLL_SECONDS=30
COMPUTE_WORKER_MAX_ATTEMPTS=4
```

El worker mantiene una conexion PostgreSQL para `LISTEN resource_requests`. La fila en
`resource_requests` es la garantia durable: si se pierde una notificacion, el polling de
respaldo encuentra el trabajo como maximo 30 segundos despues.

## Visualizador como cliente externo

```powershell
python -m http.server 5173 --directory src/compute_provisioner/web/simulator
```

Abrir, reemplazando el dominio:

```text
http://localhost:5173/?api=https://api-production.up.railway.app
```

La vista de capacidad se abre con:

```text
http://localhost:5173/capacity.html?api=https://api-production.up.railway.app
```

La cantidad de instancias de API se descubre observando el header `X-Instance-ID` de las
respuestas. Con varias replicas en Railway, el balanceador irá mostrando los distintos
procesos atendiendo las consultas.

La API debe incluir exactamente el origen local utilizado dentro de
`COMPUTE_CORS_ALLOWED_ORIGINS`.

## Verificacion

1. `GET https://<api>/health/live` prueba el proceso.
2. `GET https://<api>/health/ready` prueba proceso y PostgreSQL.
3. Crear una request desde el visualizador.
4. Confirmar en logs que el worker recibe `NOTIFY`.
5. Confirmar `PENDING -> PROVISIONING -> ACTIVE`.
6. Abrir la vista de capacidad y confirmar pool, cola y capacidad del provider.

No habilitar dominios publicos para PostgreSQL, Worker ni Provider.
