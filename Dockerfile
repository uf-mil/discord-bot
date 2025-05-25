FROM python:3.12
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore -r /app/requirements.txt
COPY . /app
WORKDIR /app
CMD ["python", "-m", "src.bot"]
