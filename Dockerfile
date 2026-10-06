FROM python:3.11
ADD . /app
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 5000 22
CMD ["python", "app.py"]
