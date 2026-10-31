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

El proveedor conserva recursos en memoria y aplica idempotencia por clave.

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

