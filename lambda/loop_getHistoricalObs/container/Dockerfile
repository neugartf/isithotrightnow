FROM python:3.12-slim
WORKDIR /app
RUN pip3 install --upgrade pip
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY handler.py .

CMD exec gunicorn --timeout 60 --log-level debug --bind :$PORT --workers 2 --threads 2 handler:app
#CMD ["gunicorn","--log-level=debug", "-w", "1", "-b", ":$PORT", "handler:app"]
