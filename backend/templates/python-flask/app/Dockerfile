FROM python:3.15-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY entrypoint.sh app.py ./
EXPOSE 5000
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["python", "app.py"]
