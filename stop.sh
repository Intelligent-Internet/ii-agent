docker ps --filter "label=com.docker.compose.project=agent" -q | xargs docker stop
COMPOSE_PROJECT_NAME=agent docker compose -f docker/docker-compose.yaml down
