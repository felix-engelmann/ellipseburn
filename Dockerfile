FROM python:latest
RUN mkdir -p /app/templates
WORKDIR /app
ADD requirements.txt /app
ADD burn.py /app
ADD templates/main.html /app/templates/
RUN pip3 install -r requirements.txt
CMD ["gunicorn", "-w 4", "-b", "0.0.0.0:8000", "burn:app"]
