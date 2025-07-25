FROM nginx:alpine

COPY docker/nginx/nginx.conf.template /etc/nginx/conf.d/default.conf.template
COPY docker/nginx/docker-entrypoint.sh /docker-entrypoint.sh

# Make entrypoint executable
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
