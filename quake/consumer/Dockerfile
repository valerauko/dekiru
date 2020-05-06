FROM python:buster

RUN pip3 install kafka-python rethinkdb
ADD consumer.py .

CMD ["python3", "consumer.py"]
