Write-Host "Stopping container..."
docker compose down

Write-Host "Cleaning up old layers and build cache..."
docker system prune -f

Write-Host "Rebuilding and starting..."
docker compose up --build
