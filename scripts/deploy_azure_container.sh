#!/usr/bin/env bash
set -euo pipefail

# Uso:
# ./scripts/deploy_azure_container.sh <resource_group> <location> <acr_name> <container_app_name> <image_name> [port]

if [[ $# -lt 5 ]]; then
  echo "Uso: $0 <resource_group> <location> <acr_name> <container_app_name> <image_name> [port]"
  echo "Ejemplo: $0 rg-lab eastus acrlabdemo lab-analyzer-api lab-analyzer 8000"
  exit 1
fi

RESOURCE_GROUP="$1"
LOCATION="$2"
ACR_NAME="$3"
CONTAINER_APP_NAME="$4"
IMAGE_NAME="$5"
PORT="${6:-8000}"

az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
az acr create --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --sku Basic --admin-enabled true

az acr build \
  --resource-group "$RESOURCE_GROUP" \
  --registry "$ACR_NAME" \
  --image "$IMAGE_NAME:latest" \
  .

ACR_LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query loginServer -o tsv)"
ACR_USER="$(az acr credential show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query username -o tsv)"
ACR_PASS="$(az acr credential show --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" --query 'passwords[0].value' -o tsv)"

az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

if ! az containerapp env show --name "${CONTAINER_APP_NAME}-env" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  az containerapp env create \
    --name "${CONTAINER_APP_NAME}-env" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION"
fi

az containerapp create \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "${CONTAINER_APP_NAME}-env" \
  --image "$ACR_LOGIN_SERVER/$IMAGE_NAME:latest" \
  --target-port "$PORT" \
  --ingress external \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --env-vars PORT="$PORT"

FQDN="$(az containerapp show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn -o tsv)"
echo "Despliegue listo: https://$FQDN"
