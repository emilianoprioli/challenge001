# Compute Provisioner

Microservicio interno para solicitar y consultar capacidad de cómputo.

## Estado actual

El flujo implementa solicitudes idempotentes, validación transaccional de política y
cuota, desired state, procesamiento asíncrono, proveedor simulado, retries y
reconciliación. API, worker y proveedor pueden desplegarse como servicios independientes.

## Circuito local completo

Ejecutar en tres terminales:

```powershell
uvicorn compute_provisioner.main:app --reload --port 8000
```

```powershell
uvicorn compute_provisioner.provider_simulator:app --reload --port 8001
```

```powershell
python -m compute_provisioner.worker
```

Abrir `http://localhost:8000/simulator`. El worker utiliza `LISTEN/NOTIFY` y conserva un
polling de respaldo. PostgreSQL es la fuente durable de trabajo.

## Simulador del proveedor externo

Se ejecuta como un proceso separado para que sus fallos no sean fallos internos de la API:

```powershell
uvicorn compute_provisioner.provider_simulator:app --port 8001
```

`PUT /resources/{idempotency_key}` acepta el header `X-Provider-Scenario`:

- `healthy`: respuesta normal;
- `slow`: demora controlada de 2 segundos;
- `timeout`: demora de 30 segundos para superar el timeout del cliente;
- `error`: respuesta `503`.

El proveedor persiste sus recursos e idempotencia en PostgreSQL, por lo que sus réplicas
son intercambiables. También limita concurrencia y longitud de cola por réplica; al
agotarse ambas responde `429` con
`Retry-After`, permitiendo estudiar backpressure sin agotar el contenedor.

## Observabilidad de capacidad

`GET /api/v1/platform/snapshot` agrega una fotografía operativa del sistema:

- instancia de API que respondió;
- uso del pool de PostgreSQL;
- solicitudes pendientes, en procesamiento y en estado desconocido;
- antigüedad del trabajo pendiente;
- concurrencia, cola, rechazos y operaciones completadas por el proveedor.
- servicios, deployments, replicas y consumo CPU/RAM del entorno Railway, si se configura
  un Project Token en la API.

El visualizador de capacidad está disponible en `/simulator/capacity.html`. Ejecutado como
cliente local también acepta `?api=https://<dominio-api>` y descubre qué réplicas de API
responden detrás del balanceador.

Cada solicitud conserva además la réplica real de API, Worker y Provider que participó en
su recorrido. El visualizador de flujo usa esas identidades persistidas; no distribuye los
puntos mediante un round-robin ficticio.

## Perfiles de fallos

El visualizador permite elegir un perfil por solicitud. El worker sortea un escenario nuevo
en cada intento y registra el resultado elegido en PostgreSQL.

| Perfil | Healthy | Lento | Error 503 | Timeout |
| --- | ---: | ---: | ---: | ---: |
| `normal` | 100% | 0% | 0% | 0% |
| `degraded` | 80% | 15% | 3% | 2% |
| `critical` | 30% | 40% | 20% | 10% |

Los escenarios determinísticos siguen disponibles para pruebas específicas. El objetivo es
observar degradación lógica sin provocar OOM ni saturar deliberadamente la infraestructura.

## Ejecución local con Docker

```powershell
docker compose up --build
```

Endpoints:

- `GET http://localhost:8000/simulator`
- `GET http://localhost:8000/health/live`
- `GET http://localhost:8000/health/ready`
- `GET http://localhost:8000/docs`

## Ejecución local con Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,database]"
uvicorn compute_provisioner.main:app --reload
```

## Tests

```powershell
pytest
```

## Base de datos

La migración inicial crea:

- `departments`;
- `applications`;
- `application_resource_policies`;
- `application_resource_desired`;
- `application_resource_observations`;
- `request_statuses`;
- `resource_requests`;
- `audit_events`.

Con PostgreSQL disponible:

```powershell
alembic upgrade head
```

Para inspeccionar el SQL sin conectarse:

```powershell
alembic upgrade head --sql
```

