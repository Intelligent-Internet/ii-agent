docker ps --filter "label=com.docker.compose.project=ii-agent" -q | xargs docker stop
docker compose down
