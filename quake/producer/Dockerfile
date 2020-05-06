FROM python:buster

RUN pip3 install confluent-kafka
ADD nied.py .

CMD ["python3", "nied.py"]
