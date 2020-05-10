#!/usr/bin/env python
#coding=utf-8

import os, logging, json

from datetime import datetime, timezone

from kafka import KafkaConsumer, TopicPartition
from rethinkdb import RethinkDB

def ensure_db(r, conn):
    result = r.db_list().contains(RETHINK_DB).do(lambda exists:
        r.branch(
            exists,
            { 'dbs_created': 0 },
            r.db_create('quake')
        )
    ).run(conn)

    if result['dbs_created']:
        logging.info('Created database')

def ensure_table(r, conn):
    result = r.db(RETHINK_DB).table_list().contains(RETHINK_TABLE).do(lambda exists:
        r.branch(
            exists,
            { 'tables_created': 0 },
            r.db(RETHINK_DB).table_create(RETHINK_TABLE)
        )
    ).run(conn)

    if result['tables_created']:
        logging.info('Created table')

    return result['tables_created']

if __name__ == '__main__':
    FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
    logging.basicConfig(level=logging.INFO, format=FORMAT)

    RETHINK_HOST = os.environ['RETHINK_HOST'] # 'localhost'
    RETHINK_PORT = os.environ['RETHINK_PORT'] # 28015
    RETHINK_DB = os.environ['RETHINK_DB'] # 'quake'
    RETHINK_TABLE = os.environ['RETHINK_TABLE'] # 'quakes'

    r = RethinkDB()
    conn = r.connect(
        RETHINK_HOST,
        RETHINK_PORT
    )

    c = KafkaConsumer(
        bootstrap_servers=os.environ['KAFKA_BOOTSTRAP'],
        group_id='single_consumer',
        security_protocol='SASL_SSL',
        sasl_mechanism='PLAIN',
        sasl_plain_username=os.environ['KAFKA_API_KEY'],
        sasl_plain_password=os.environ['KAFKA_API_SECRET'],
        value_deserializer=json.loads
    )

    c.assign([TopicPartition('quakes', 0)])

    # if db table doesn't exist try backfilling it from kafka
    ensure_db(r, conn)
    if ensure_table(r, conn):
        c.seek_to_beginning()

    try:
        for msg in c:
            if msg is None:
                continue

            record = { key: msg.value[key] for key in ['id', 'ver', 'name', 'shindo', 'magnitude'] if key in {*msg.value} }
            if msg.value['lon']:
                record['location'] = r.point(msg.value['lon'], msg.value['lat'])
            record['occurred_at'] = datetime.fromtimestamp(msg.value['time'], timezone.utc)
            record['updated_at'] = r.now()

            logging.info("Upserting record %s", record)
            r.db(RETHINK_DB).table(RETHINK_TABLE)\
                .insert(record, conflict="update").run(conn)
    finally:
        c.close()
