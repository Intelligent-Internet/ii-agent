docker ps --filter "label=com.docker.compose.project=scribe-salon" -q | xargs docker stop
docker compose down
