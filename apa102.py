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
# based on https://github.com/tinue/APA102_Pi

import time
import json
import sys
import os, signal
from subprocess import call
import spidev

from math import ceil

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
    "configfile": "/etc/lcars/" + name.lower() + ".yml",
    "colors": {
        "green": 0x00FF00,
        "yellow": 0xFFAA00,
        "orange": 0xFF3300,
        "red": 0xFF0000,
        "blue": 0x0000FF
      }
    }


parser = ArgumentParser(description=name + ' driver.\n\nDefaults in {curly braces}',formatter_class=RawTextHelpFormatter)
parser.add_argument("-i", "--interval", type=float, default=cfg['interval'],
                            help="check interval in s (float, default "+str(cfg['interval'])+")", metavar="x")
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


def exit_gracefully(a=False,b=False):
  print("exit gracefully...")
  client.disconnect()
  clearStrip()
  exit(0)

def exit_hard():
  exit(1)

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

nleds = cfg['leds']
timeout_s = cfg['timeout_s']

MAX_BRIGHTNESS = 31 # Safeguard: Max. brightness that can be selected. 
G_BN = cfg['brightness']
LED_START = 0b11100000 # Three "1" bits, followed by 5 brightness bits
LED_ARR = [LED_START,0,0,0] * nleds # Pixel buffer

def setPixel(lednr, red, green, blue, bright_percent=100):
  if lednr < 0 or lednr >= nleds:
    return
  brightness = int(ceil(bright_percent*G_BN/100.0))
  ledstart = (brightness & 0b00011111) | LED_START
  start_index = 4 * lednr
  LED_ARR[start_index] = ledstart
  LED_ARR[start_index + 3] = red
  LED_ARR[start_index + 2] = green
  LED_ARR[start_index + 1] = blue

def show():
  spi.xfer([0] * 4) # clock_start_frame
  spi.xfer(list(LED_ARR)) # xfer2 kills the list, unfortunately. So it must be copied first
  for _ in range((nleds + 15) // 16): # clock_end_frame
    spi.xfer([0x00])

def clearStrip():
  for led in range(nleds):
    setPixel(led,0,0,0,0)
  show()

def str2hexColor(strcolor):
  colors = cfg['colors']
  if not strcolor in colors:
    eprint(strcolor, "not found in", colors)
    return False
  intcol = colors[strcolor]
  return( (intcol & 0xFF0000) >> 16, (intcol & 0x00FF00) >> 8, intcol & 0x0000FF)

def setAllColor(color):
  (red, green, blue) = str2hexColor(color)
  for led in range(nleds):
    setPixel(led,red,green,blue,100)
  show()

def getColorFromThreshold(value):
  nt = len(thresholds)
  color = ''
  for i in range(nt):
    ct = thresholds[i][0]
    if value >= ct:
      color = thresholds[i][1]
    else:
      break
  print("new color:", color)
  return(color)

last_update = time.time()
def on_message(client, userdata, msg):
  global last_update
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
    last_update = time.time()

  except Exception as e:
    eprint(e)

def subscribing():
  client.on_message = on_message
  client.loop_forever()

error_colors = [ "red", "green", "blue" ]
nr_err_col = len(error_colors)
err_col_runner = 0

setAllColor("red")
time.sleep(0.33)
setAllColor("green")
time.sleep(0.33)
setAllColor("blue")
time.sleep(0.33)


MEAS_INTERVAL = cfg['interval']
def main():
  global err_col_runner
  while True:
    run_started_at = time.time()

    if last_update + timeout_s < run_started_at:
      print("timeout!")
      c_err_col = error_colors[err_col_runner]
      err_col_runner += 1
      if err_col_runner == nr_err_col:
        err_col_runner = 0
      print("setColor", c_err_col, str2hexColor(c_err_col))
      setAllColor(c_err_col)

    n.notify("WATCHDOG=1")

    run_finished_at = time.time()
    run_duration = run_finished_at - run_started_at

    DEBUG and print("duration of run: {:10.4f}s.".format(run_duration))

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
