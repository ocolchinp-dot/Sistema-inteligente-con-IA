# Sistema inteligente con IA - Analizador de resultados de laboratorio

Proyecto full-stack con **Frontend Web + API FastAPI + workflow agentic** para analizar resultados de laboratorio desde archivos PDF o imagen y devolver una salida estructurada, validada y explicable.

## Arquitectura

```text
frontend (HTML/CSS/JS)
    -> POST /api/analyze (multipart)
backend (FastAPI)
    -> Agent Orchestrator (agent.py)
        -> Tool 1: extract_content_tool
        -> Tool 2: classify_document_tool
        -> LLM extraction (OpenAI, JSON Schema)
        -> Tool 3: normalize_date_tool
        -> Tool 4: range_validator_tool
        -> Tool 5: clarifying_questions_tool
    -> Pydantic contract validation (AnalyzeResponse)
```

## Stack técnico

- **Backend**: Python + FastAPI + Pydantic.
- **Frontend**: HTML/CSS/JS (simple y desplegable en cualquier servidor estático).
- **LLM**: OpenAI Responses API (`gpt-4.1-mini` por defecto) con salida estructurada.
- **Agentic Engineering**: orquestación por pasos con decisiones condicionales (`success`, `needs_review`, `error`).
- **Tool Calling**: tools explícitas con trazabilidad en `tool_trace`.

## Contrato de salida (validado)

La API retorna exactamente estas llaves top-level:

- `status`
- `document_type`
- `summary`
- `extracted_data`
- `warnings`
- `needs_clarification`
- `clarifying_questions`
- `tool_trace`

El contrato se valida con `AnalyzeResponse` (`backend/app/schemas.py`).

## Flujo del sistema

1. El usuario sube un archivo en la UI.
2. FastAPI recibe el archivo.
3. `extract_content_tool` extrae texto/metadatos.
4. `classify_document_tool` define tipo de documento.
5. El agente llama al LLM para extracción estructurada (o fallback heurístico).
6. `normalize_date_tool` normaliza fechas.
7. `range_validator_tool` busca inconsistencias y valores fuera de rango.
8. `clarifying_questions_tool` genera preguntas cuando faltan datos.
9. El agente decide:
   - `success` si documento claro,
   - `needs_review` si ambiguo/incompleto,
   - `error` si archivo inválido.
10. UI muestra JSON, advertencias y preguntas.

## Estructura del repositorio

```text
backend/
  app/
    main.py
    agent.py
    schemas.py
    tools.py
  requirements.txt
frontend/
  index.html
  styles.css
  app.js
samples/
  lab_sample.txt
scripts/
  deploy_azure_container.sh
Dockerfile
.dockerignore
README.md
```

## Subir a GitHub (comandos rápidos)

Si ya creaste el repo vacío en GitHub (sin README), ejecuta desde la carpeta del proyecto:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<TU_USUARIO>/<TU_REPO>.git
git push -u origin main
```

Si ya tienes git inicializado y solo quieres enlazar/pushear:

```bash
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/<TU_USUARIO>/<TU_REPO>.git
git push -u origin $(git branch --show-current)
```

## Ejecución local

### 1) Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Variables opcionales:

- `OPENAI_API_KEY`: habilita extracción LLM real.
- `OPENAI_MODEL`: default `gpt-4.1-mini`.

> Sin `OPENAI_API_KEY`, el sistema usa extracción heurística para no romper la app.

### 2) Frontend

En otra terminal:

```bash
cd frontend
python -m http.server 5500
```

Abrir: `http://localhost:5500`

## Docker (1 contenedor para API)

Construir imagen:

```bash
docker build -t lab-analyzer:latest .
```

Ejecutar local:

```bash
docker run --rm -p 8000:8000 \
  -e OPENAI_API_KEY="<TU_API_KEY>" \
  -e OPENAI_MODEL="gpt-4.1-mini" \
  lab-analyzer:latest
```

Probar healthcheck:

```bash
curl http://localhost:8000/health
```

## Deploy en Azure Container Apps

Prerequisitos:

- Azure CLI (`az`) instalada.
- Sesión iniciada: `az login`.

Script incluido para desplegar a Azure con ACR + Container App:

```bash
./scripts/deploy_azure_container.sh \
  <resource_group> \
  <location> \
  <acr_name_unico> \
  <container_app_name> \
  <image_name> \
  8000
```

Ejemplo:

```bash
./scripts/deploy_azure_container.sh rg-lab eastus acrlabdemo lab-analyzer-api lab-analyzer 8000
```

El script:

1. Crea Resource Group.
2. Crea Azure Container Registry.
3. Construye la imagen en ACR.
4. Crea entorno de Container Apps.
5. Despliega el contenedor con ingress público.

## Uso

1. Selecciona PDF o imagen desde la UI.
2. Presiona **Analizar documento**.
3. Observa estado de procesamiento.
4. Revisa salida estructurada JSON + advertencias + preguntas de aclaración.

## Ejemplos de comportamiento

- **Caso claro**: `status=success`, `needs_clarification=false`.
- **Caso ambiguo/incompleto**: `status=needs_review`, `needs_clarification=true`, `clarifying_questions>=2`.
- **Caso error**: `status=error`, warning explícito.

## API

### `POST /api/analyze`

`multipart/form-data` con campo `file`.

Respuesta: JSON estructurado validado conforme al contrato descrito.

### `GET /health`

Healthcheck básico del backend.
