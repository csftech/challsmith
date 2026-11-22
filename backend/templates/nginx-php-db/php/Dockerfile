FROM php:8.6-fpm-alpine
RUN docker-php-ext-install pdo_mysql mysqli \
 && printf '[www]\nclear_env = no\n' > /usr/local/etc/php-fpm.d/zz-env.conf
COPY entrypoint.sh /entrypoint.sh
COPY index.php /app/index.php
ENTRYPOINT ["sh", "/entrypoint.sh"]
CMD ["php-fpm"]
