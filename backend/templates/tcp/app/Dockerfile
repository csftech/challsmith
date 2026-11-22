FROM alpine:3.24
RUN apk add --no-cache socat
COPY entrypoint.sh run.sh /app/
EXPOSE 9000
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["socat", "TCP-LISTEN:9000,reuseaddr,fork", "EXEC:sh /app/run.sh"]
