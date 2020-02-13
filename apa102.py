#!/usr/bin/python3
# coding=utf-8
#
# Copyright © 2018 UnravelTEC
# Michael Maier <michael.maier+github@unraveltec.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# If you want to relicense this code under another license, please contact info+github@unraveltec.com.

import time
import json
import sys
import os, signal
from subprocess import call
import spidev

from argparse import ArgumentParser, RawTextHelpFormatter
import textwrap

import pprint

import sdnotify

import threading

def eprint(*args, **kwargs):
  print(*args, file=sys.stderr, **kwargs)
  sys.stderr.flush()

# config order (later overwrites newer)
# 1. default cfg
# 2. config file
# 3. cmdline args
# 4. runtime cfg via MQTT $host/sensors/$name/config

name = "APA102" # Uppercase
cfg = {
    "interval": 1,
    "bus": 0,
    "address": 0,
    "busfreq": 400000,
    "brokerhost": "localhost",
    "leds": 1,
    "timeout_s": 3,
    "brightness": 100,
    "configfile": "/etc/lcars/" + name.lower() + ".yml"
    }


parser = ArgumentParser(description=name + ' driver.\n\nDefaults in {curly braces}',formatter_class=RawTextHelpFormatter)
parser.add_argument("-i", "--interval", type=float, default=cfg['interval'],
                            help="measurement interval in s (float, default "+str(cfg['interval'])+")", metavar="x")
parser.add_argument("-D", "--debug", action='store_true', #cmdline arg only, not in config
                            help="print debug messages")

parser.add_argument("-b", "--bus", type=int, default=cfg['bus'], choices=[0,1,2,3,4,5,6],
                            help="spi bus # (/dev/spidev[0-6], {"+str(cfg['bus'])+"} )", metavar="n")
parser.add_argument("-a", "--address", type=int, default=cfg['address'], choices=[0,1,2],
                            help="spi cs line 0-2 {"+str(cfg['address'])+"}", metavar="i")
parser.add_argument("-s", "--busfreq", type=int, default=cfg['busfreq'],
                            help="bus frequenzy {"+str(cfg['busfreq'])+"} Hz", metavar="f")

parser.add_argument("-o", "--brokerhost", type=str, default=cfg['brokerhost'],
                            help="use mqtt broker (addr: {"+cfg['brokerhost']+"})", metavar="addr")

parser.add_argument("-c", "--configfile", type=str, default=cfg['configfile'],
                            help="load configfile ("+cfg['configfile']+")", metavar="nn")

args = parser.parse_args()

if os.path.isfile(args.configfile) and os.access(args.configfile, os.R_OK):
  with open(args.configfile, 'r') as ymlfile:
    import yaml
    filecfg = yaml.load(ymlfile)
    print("opened configfile", args.configfile)
    for key in cfg:
      if key in filecfg:
        cfg[key] = filecfg[key]
        print("used file setting", key, cfg[key])
    for key in filecfg:
      if not key in cfg:
        cfg[key] = filecfg[key]
        print("loaded file setting", key, cfg[key])
else:
  print("no configfile found at", args.configfile)

argdict = vars(args)
for key in cfg:
  if key in argdict and argdict[key] != cfg[key]:
    cfg[key] = argdict[key]
    print('cmdline param', key, 'used with', argdict[key])

print("config used:", cfg)


n = sdnotify.SystemdNotifier()

DEBUG = args.debug

hostname = os.uname()[1]

if not 'target' in cfg:
  eprint('no target in cfg, exit')
  exit(1)
target = cfg['target']
if not 'tags' in target or not 'sensor' in target['tags']:
  eprint('no sensor in cfg, exit')
  exit(1)
if not 'measurement' in target or not 'value' in target:
  eprint('no measurement or value in cfg, exit')
  exit(1)

if not 'thresholds' in cfg:
  eprint('no thresholds in cfg, exit')
  exit(1)

tags = target['tags']
sensor = tags['sensor']
del tags['sensor'] # implied by topic, no need to store
measurement = target['measurement']
valuekey = target['value']
subscribe_topic = '/'.join([hostname, 'sensors', sensor, measurement]) 
print('subscribe to:', subscribe_topic)

thresholds = cfg['thresholds']

spi = spidev.SpiDev()
DEBUG and print('after spi declare')
spi.open(cfg['bus'], cfg['address'])
DEBUG and print('after spi open')
spi.max_speed_hz = cfg['busfreq']
DEBUG and print('after spi hz')
spi.mode = 1
DEBUG and print('after spi mode')

brokerhost = cfg['brokerhost']
def on_connect(client, userdata, flags, rc):
  print('on_connect')
  try:
    print("Connected to MQTT broker "+brokerhost+" with result code "+str(rc))
    client.subscribe(subscribe_topic)
    print("subscribed to", subscribe_topic)
  except Exception as e:
    eprint('Exception', e)

import paho.mqtt.client as mqtt
client = mqtt.Client(client_id=name, clean_session=True) # client id only useful if subscribing, but nice in logs # clean_session if you don't want to collect messages if daemon stops
client.connect(brokerhost,1883,60)
client.on_connect = on_connect


# client.loop_start() # needed when we have long time no msg


def exit_gracefully(a=False,b=False):
  print("exit gracefully...")
  client.disconnect()
  exit(0)

def exit_hard():
  exit(1)

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

leds = cfg['leds']
timeout_s = cfg['timeout_s']

def clock_start_frame():
  spi.xfer([0] * 4)

MEAS_INTERVAL = cfg['interval']

def getColorFromThreshold(value):
  nt = len(thresholds)
  # print(nt)
  color = ''
  for i in range(nt):
    # print(i)
    ct = thresholds[i][0]
    if value >= ct:
      color = thresholds[i][1]
    else:
      break
  return(color)


getColorFromThreshold(99)

def on_message(client, userdata, msg):
  try:
    DEBUG and print( msg.topic, msg.payload.decode())
    topic_array = msg.topic.split('/')
    payload_string = msg.payload.decode()
    payload_json = json.loads(payload_string)
    # print("got", payload_json)
    msgtags = payload_json['tags']
    globaltags = tags
    # print(msgtags, globaltags)
    for key in globaltags:
      # v = globaltags[key]
      if not key in msgtags:
        print('filter', key, 'not found in msg tags, ignoring')
        return
    values = payload_json['values']
    if not valuekey in values:
      print('value', valuekey, 'not found in msg values, ignoring')
      return
    v = values[valuekey]
    print(valuekey, v, getColorFromThreshold(v))


  except Exception as e:
    eprint(e)

def subscribing():
  client.on_message = on_message
  client.loop_forever()

def main():
  while True:
    run_started_at = time.time()


    print("color:blue")

    n.notify("WATCHDOG=1")

    run_finished_at = time.time()
    run_duration = run_finished_at - run_started_at

    DEBUG and print("duration of run: {:10.4f}s.".format(run_duration))

    # exit_gracefully() #rm in prod, only 4 test

    to_wait = MEAS_INTERVAL - run_duration
    if to_wait > 0:
      DEBUG and print("wait for "+str(to_wait)+"s")
      time.sleep(to_wait - 0.002)
    else:
      DEBUG and print("no wait, {0:4f}ms over".format(- to_wait*1000))

sub=threading.Thread(target=subscribing)
pub=threading.Thread(target=main)

### Start MAIN ###

sub.start()
pub.start()

print("started threads")

n.notify("READY=1") #optional after initializing
