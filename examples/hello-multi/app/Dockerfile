FROM php:8.6-fpm-alpine
RUN docker-php-ext-install pdo_mysql \
 && printf '[www]\nclear_env = no\n' > /usr/local/etc/php-fpm.d/zz-env.conf
COPY index.php /app/index.php
