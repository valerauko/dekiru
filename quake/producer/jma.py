#!/usr/bin/env python
#coding=utf-8

import urllib.request as request
import xml.etree.ElementTree as et
import dateutil.parser as dateparser
import time, re, os, logging, json
from confluent_kafka import Producer

QUAKE_URL = 'http://www.data.jma.go.jp/developer/xml/feed/eqvol.xml'
NS = {'atom': 'http://www.w3.org/2005/Atom',
      'jmx': 'http://xml.kishou.go.jp/jmaxml1/',
      'seism': 'http://xml.kishou.go.jp/jmaxml1/body/seismology1/',
      'eb': 'http://xml.kishou.go.jp/jmaxml1/elementBasis1/',
      'ib': 'http://xml.kishou.go.jp/jmaxml1/informationBasis1/'}
CHECK_INTERVAL = 30
QUAKE_TITLES = [
    '震源・震度に関する情報',
    '震源に関する情報',
    '震度速報',
    '緊急地震速報（予報）',
    '緊急地震速報（警報）'
]

def fetch_xml(url=QUAKE_URL):
    with request.urlopen(url) as response:
        logging.debug("Loaded %s", url)
        raw_data = response.read()
        return et.fromstring(raw_data)

def is_new(str):
    date = dateparser.isoparse(str)
    return date.timestamp() > time.time() - CHECK_INTERVAL

# Head/InfoType
# - 発表 -> normal
# - 取消 -> delete
#
# Head/InfoKind
# - 緊急地震速報 || 地震情報 OK
#   id: Head/EventID
#   name: Body/Earthquake/Hypocenter/Area/Name | ReduceName
#   time: Body/Earthquake/OriginTime
#   coords: Body/Earthquake/Hypocenter/Area/Coordinate
#   shindo: Body/Intensity/Forecast/ForecastInt/From
#   magnitude: Body/Earthquake/Magnitude
# - 震度速報
#   id: Head/EventID
#   name: n/a
#   time: n/a
#   coords: n/a
#   shindo: Body/Intensity/Observation/MaxInt
#   magnitude: n/a
# - 震源速報
#   id: Head/EventID
#   name: Body/Earthquake/Hypocenter/Area/Name | ReduceName
#   time: Body/Earthquake/OriginTime
#   coords: Body/Earthquake/Hypocenter/Area/Coordinate
#   shindo: n/a
#   magnitude: Body/Earthquake/Magnitude

ID_PATH = 'ib:Head/ib:EventID'
TYPE_PATH = 'ib:Head/ib:InfoType'
KIND_PATH = 'ib:Head/ib:InfoKind'
VERSION_PATH = 'ib:Head/ib:Serial'

AREA_PATH = 'seism:Body/seism:Earthquake/seism:Hypocenter/seism:Area/seism:Name'
TIME_PATH = 'seism:Body/seism:Earthquake/seism:OriginTime'
COORDS_PATH = 'seism:Body/seism:Earthquake/seism:Hypocenter/seism:Area/eb:Coordinate'
SHINDO_PATH = 'seism:Body/seism:Intensity/seism:Observation/seism:MaxInt'
MAGNITUDE_PATH = 'seism:Body/seism:Earthquake/eb:Magnitude'

ALT_TIME_PATH = 'ib:Head/ib:TargetDateTime'
ALT_AREA_PATH = 'ib:Head/ib:Headline/ib:Information/ib:Item/ib:Areas/ib:Area/ib:Name'

def parse_coords(coords):
    return map(float, re.match('([+-]\d{2}(?:\.\d))([+-]\d{3}(?:\.\d))', coords).groups())

def retraction(xml):
    return {
        'id': xml.find(ID_PATH, NS).text,
        'ver': 'retracted'
    }

def shindo_only(xml):
    return {
        'id': xml.find(ID_PATH, NS).text,
        'ver': xml.find(VERSION_PATH, NS).text,
        'name': xml.find(ALT_AREA_PATH, NS).text,
        'time': dateparser.isoparse(xml.find(ALT_TIME_PATH, NS).text).timestamp,
        'shindo': xml.find(SHINDO_PATH, NS).text
    }

def hypocenter(xml):
    coords = xml.find(COORDS_PATH, NS).text
    [lat, lon] = parse_coords(coords)

    return {
        'id': xml.find(ID_PATH, NS).text,
        'ver': xml.find(VERSION_PATH, NS).text,
        'name': xml.find(AREA_PATH, NS).text,
        'time': dateparser.isoparse(xml.find(TIME_PATH, NS).text).timestamp,
        'lat': lat,
        'lon': lon,
        'magnitude': float(xml.find(MAGNITUDE_PATH, NS).text)
    }


def full_report(xml):
    coords = xml.find(COORDS_PATH, NS).text
    [lat, lon] = parse_coords(coords)

    return {
        'id': xml.find(ID_PATH, NS).text,
        'ver': xml.find(VERSION_PATH, NS).text,
        'name': xml.find(AREA_PATH, NS).text,
        'time': dateparser.isoparse(xml.find(TIME_PATH, NS).text).timestamp,
        'lat': lat,
        'lon': lon,
        'shindo': xml.find(SHINDO_PATH, NS).text,
        'magnitude': float(xml.find(MAGNITUDE_PATH, NS).text)
    }

def fetch_detail(url):
    xml = fetch_xml(url)

    if xml.find(TYPE_PATH, NS).text == '取消':
        return retraction(xml)

    kind = xml.find(KIND_PATH, NS).text
    if kind == '震度速報':
        return shindo_only(xml)
    elif kind == '震源速報':
        return hypocenter(xml)
    else:
        # there might be other cases, probably fails then
        return full_report(xml)

if __name__ == '__main__':
    os.environ['TZ'] = 'Asia/Tokyo'
    time.tzset()

    FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=FORMAT)

    p = Producer({
        'bootstrap.servers': os.environ['KAFKA_BOOTSTRAP'],
        'sasl.mechanisms': 'PLAIN',
        'security.protocol': 'SASL_SSL',
        'sasl.username': os.environ['KAFKA_API_KEY'],
        'sasl.password': os.environ['KAFKA_API_SECRET'],
    })

    while 1:
        time.sleep(CHECK_INTERVAL)

        xml = fetch_xml()
        for entry in xml.iterfind('atom:entry', NS):
            if entry.find('atom:title', NS).text not in QUAKE_TITLES:
                continue
            if not is_new(entry.find('atom:updated', NS).text):
                break

            report = fetch_detail(entry.find('atom:link', NS).attrib['href'])
            logging.info("Writing to Kafka %s", report)
            p.produce(os.environ['KAFKA_TOPIC'], value=json.dumps(report))

        p.flush()
