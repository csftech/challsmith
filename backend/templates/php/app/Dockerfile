FROM php:8.6-cli-alpine
COPY entrypoint.sh /entrypoint.sh
COPY index.php /var/www/html/index.php
EXPOSE 80
ENTRYPOINT ["sh", "/entrypoint.sh"]
CMD ["php", "-S", "0.0.0.0:80", "-t", "/var/www/html"]
