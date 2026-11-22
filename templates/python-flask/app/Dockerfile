FROM python:3.15.2-alpine3.24
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY entrypoint.sh app.py ./
EXPOSE 5000
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["python", "app.py"]
