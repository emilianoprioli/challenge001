# Compute Provisioner

Microservicio interno para solicitar y consultar capacidad de cómputo.

## Estado actual

El primer hito contiene únicamente:

- aplicación FastAPI;
- configuración mediante variables de entorno;
- endpoints de liveness y readiness;
- imagen de container ejecutada sin privilegios;
- PostgreSQL para el entorno local;
- modelos SQLAlchemy del dominio acordado;
- migración inicial de Alembic;
- pruebas HTTP y de metadata.

Todavía no implementa endpoints de solicitudes ni llamadas al proveedor externo.

## Ejecución local con Docker

```powershell
docker compose up --build
```

Endpoints:

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

