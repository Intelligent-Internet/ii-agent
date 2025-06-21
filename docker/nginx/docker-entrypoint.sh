#!/bin/sh

# Substitute environment variables in template
echo "Substituting environment variables in template"
echo "PUBLIC_DOMAIN: ${PUBLIC_DOMAIN}"
export ESCAPED_PUBLIC_DOMAIN=$(echo "${PUBLIC_DOMAIN}" | sed 's/\./\\./g')
echo "ESCAPED_PUBLIC_DOMAIN: ${ESCAPED_PUBLIC_DOMAIN}"
envsubst '${PUBLIC_DOMAIN} ${ESCAPED_PUBLIC_DOMAIN} ' </etc/nginx/conf.d/default.conf.template >/etc/nginx/conf.d/default.conf

# Show the generated config for debugging
echo "Generated nginx config:"
cat /etc/nginx/conf.d/default.conf

# Test nginx configuration
exec nginx -g 'daemon off;'
