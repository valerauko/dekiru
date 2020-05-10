FROM python:buster

RUN pip3 install confluent-kafka

ARG provider=nied
ADD $provider.py app.py

CMD ["python3", "app.py"]
