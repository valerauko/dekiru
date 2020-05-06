#!/usr/bin/env python
#coding=utf-8

import urllib.request as request
import time, json
import os, logging
from confluent_kafka import Producer, KafkaError

def current_json():
    url = time.strftime('http://www.kmoni.bosai.go.jp/webservice/hypo/eew/%Y%m%d%H%M%S.json')
    with request.urlopen(url) as response:
        logging.debug("Loaded %s", url)
        return json.load(response)

def latest():
    json = current_json()
    if json['result']['message'] != '':
        return {}
    return {
        'id': json['report_id'],
        'ver': 'final' if json['is_final'] else json['report_num'],
        'name': json['region_name'],
        'time': json['origin_time'],
        'lat': float(json['latitude']),
        'lon': float(json['longitude']),
        'shindo': json['calcintensity'],
        'magnitude': float(json['magunitude'])
    }

def should_skip(previous, current):
    # got nothing
    if not current:
        return True
    # new report
    if not previous:
        return False
    # new report
    if current['id'] != previous['id']:
        return False
    # new report update
    if current['ver'] != previous['ver']:
        return False
    # final already
    if previous['ver'] == 'final':
        return True

if __name__ == '__main__':
    TOPIC = 'quakes'
    FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)

    p = Producer({
        'bootstrap.servers': os.environ['KAFKA_BOOTSTRAP'],
        'sasl.mechanisms': 'PLAIN',
        'security.protocol': 'SASL_SSL',
        'sasl.username': os.environ['KAFKA_API_KEY'],
        'sasl.password': os.environ['KAFKA_API_SECRET'],
    })

    last_seen = {}
    while 1:
        time.sleep(1) # ignore shift due to processing time
        item = latest()

        if should_skip(last_seen, item):
            continue

        last_seen = item
        logging.info("Writing to Kafka %s", item)
        p.produce(TOPIC, value=json.dumps(item))
        p.flush()
