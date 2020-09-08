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

import sdnotify
n = sdnotify.SystemdNotifier()
n.notify("WATCHDOG=1")

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

import threading
from copy import deepcopy

n.notify("WATCHDOG=1")

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
    "interval": 0.3,
    "bus": 0,
    "address": 0,
    "busfreq": 400000,
    "brokerhost": "localhost",
    "leds": 1,
    "timeout_s": 3,
    "brightness": 100,
    "fixed": 0,
    "skip": 0, # for our 8-led boards, skip # after the 1st
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

parser.add_argument("-f", "--fixed", type=int, default=cfg['fixed'],
                            help="# of fixed leds, {"+str(cfg['fixed'])+"} )", metavar="n")

parser.add_argument("-c", "--configfile", type=str, default=cfg['configfile'],
                            help="load configfile ("+cfg['configfile']+")", metavar="nn")

args = parser.parse_args()
n.notify("WATCHDOG=1")
DEBUG = args.debug

fcfg = deepcopy(cfg) # final config used
if os.path.isfile(args.configfile) and os.access(args.configfile, os.R_OK):
  with open(args.configfile, 'r') as ymlfile:
    import yaml
    filecfg = yaml.load(ymlfile)
    print("opened configfile", args.configfile)
    for key in cfg:
      if key in filecfg:
        value = filecfg[key]
        fcfg[key] = value
        print("used file setting", key, value)
    for key in filecfg:
      if not key in cfg:
        value = filecfg[key]
        fcfg[key] = value
        print("loaded file setting", key, value)
else:
  print("no configfile found at", args.configfile)
DEBUG and print('config from default & file', fcfg)

argdict = vars(args)
for key in cfg:
  if key in argdict and argdict[key] != cfg[key]:
    value = argdict[key]
    fcfg[key] = value
    print('cmdline param', key, 'used with', value)

cfg = fcfg
required_params = ['brokerhost']
for param in required_params:
  if not param in cfg or not cfg[param]:
    eprint('param', param, 'missing from config, exit')
    exit(1)

print("config used:", cfg)
n.notify("WATCHDOG=1")


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

thresholds = cfg['thresholds']

spi = spidev.SpiDev()
DEBUG and print('after spi declare')
spi.open(cfg['bus'], cfg['address'])
DEBUG and print('after spi open')
spi.max_speed_hz = cfg['busfreq']
DEBUG and print('after spi hz')
spi.mode = 1
DEBUG and print('after spi mode')
n.notify("WATCHDOG=1")

brokerhost = cfg['brokerhost']
def onConnect(client, userdata, flags, rc):
  try:
    if rc != 0:
      eprint('mqtt: failure on connect to broker "'+ brokerhost+ '", result code:', str(rc))
      if rc == 3:
        eprint('mqtt: broker "'+ brokerhost+ '" unavailable')
    else:
      print("mqtt: Connected to broker", brokerhost, "with result code", str(rc))
      client.subscribe(subscribe_topic)
      print("mqtt: subscribing to", subscribe_topic)
      return
  except Exception as e:
    eprint('mqtt: Exception in onConnect', e)
  mqttConnect()

def onDisconnect(client, userdata, rc):
  if rc != 0:
    print("mqtt: Unexpected disconnection.")
    mqttReconnect()

def mqttConnect():
  while True:
    try:
      print("mqtt: Connecting to", brokerhost)
      client.connect(brokerhost,1883,60)
      print('mqtt: connect successful')
      break
    except Exception as e:
      eprint('mqtt: Exception in client.connect to "' + brokerhost + '", E:', e)
      print('mqtt: next connect attempt in 3s... ', end='')
      time.sleep(3)
      print('retry.')

def mqttReconnect():
  print('mqtt: attempting reconnect')
  while True:
    try:
      client.reconnect()
      print('mqtt: reconnect successful')
      break
    except ConnectionRefusedError as e:
      eprint('mqtt: ConnectionRefusedError', e, '\nnext attempt in 3s')
      time.sleep(3)

import paho.mqtt.client as mqtt
client = mqtt.Client(client_id=name, clean_session=True) # client id only useful if subscribing, but nice in logs # clean_session if you don't want to collect messages if daemon stops
client.on_connect = onConnect
client.on_disconnect = onDisconnect
mqttConnect()

RUNNING = True
def exit_gracefully(a=False,b=False):
  global RUNNING
  print("exit gracefully...")
  RUNNING = False
  print("waiting for threads... ", end='')
  time.sleep(2)
  print("finishing")
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
MAX_BRIGHTNESS = 10 # Safeguard: Max. brightness that can be selected. 
G_BN = ceil(cfg['brightness']/100)
LED_START = 0b11100000 # Three "1" bits, followed by 5 brightness bits
LED_ARR = [LED_START,0,0,0] * nleds # Pixel buffer

def setPixel(lednr, red, green, blue, bright_percent=100):
  if lednr < 0 or lednr >= nleds:
    return
  brightness = int(ceil(bright_percent*G_BN/100*MAX_BRIGHTNESS))
  if bright_percent < 10:
    factor = bright_percent / 10
    red = ceil(red * factor)
    green = ceil(green * factor)
    blue = ceil(blue * factor)
  bn_bin = brightness & 0b00011111
  ledstart = bn_bin | LED_START
  start_index = 4 * lednr
  LED_ARR[start_index] = ledstart
  LED_ARR[start_index + 3] = red
  LED_ARR[start_index + 2] = green
  LED_ARR[start_index + 1] = blue
  DEBUG and print(bn_bin, bin(bn_bin), red, green, blue)

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

def getColorFromThreshold(value):
  nt = len(thresholds)
  color = ''
  for i in range(nt):
    ct = thresholds[i][0]
    if value >= ct:
      color = thresholds[i][1]
    else:
      break
  DEBUG and print("new color:", color)
  return(color)

skip = cfg['skip']
def setAllColor(color):
  (red, green, blue) = str2hexColor(color)
  for led in range(nleds):
    if led == 0 or led > skip:
      setPixel(led,red,green,blue,100)
    else:
      setPixel(led,0,0,0,0)
  show()

max_value = cfg['maxvalue']
strip_colors = [] # [(0,0,0xFF,100)] # r,g,b, brightness
def preCalcStrip():
  global strip_colors
  fixed = cfg['fixed']
  for led in range(fixed):
    colors = (0,0,0xFF,100)
    strip_colors.append(colors)
    DEBUG and print(led, "fixed", strip_colors[led])

  step = max_value / (nleds - fixed)
  print("strip with", nleds - fixed, "LEDs, each corresponds to", step, "ppm.")
  cstep = 0
  for led in range(fixed, nleds):
    cstep += step
    colorstr = getColorFromThreshold(cstep)
    (red, green, blue) = str2hexColor(colorstr)
    strip_colors.append( (red, green, blue, G_BN*100) )
    DEBUG and print(led, round(cstep), "ppm", strip_colors[led])

preCalcStrip()

def setBarLevel(value, brightness = 100):
  if value > max_value:
    value = max_value

  fixed = cfg['fixed']
  fixedcolorstr = getColorFromThreshold(value)
  (fixr, fixg, fixb) = str2hexColor(fixedcolorstr)
  for led in range(fixed):
    setPixel(led, fixr, fixg, fixb, brightness)
    DEBUG and print(led, (fixr, fixg, fixb))

  how_many_leds_lit = ceil(value / max_value * (nleds-fixed))
  DEBUG and print(how_many_leds_lit, "how_many_leds_lit at", value)
  for led in range(fixed, how_many_leds_lit+fixed):
    cled = strip_colors[led]
    setPixel(led, cled[0], cled[1], cled[2], cled[3])
    DEBUG and print(led, cled)
  DEBUG and print("--------------------")

  for led in range(how_many_leds_lit+fixed, nleds):
    cled = strip_colors[led]
    setPixel(led, cled[0], cled[1], cled[2], 1)

  show()


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
    textcolor = getColorFromThreshold(v)
    # print(valuekey, v, getColorFromThreshold(v))
  #    setAllColor(textcolor)
    setBarLevel(v)
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


n.notify("WATCHDOG=1")
MEAS_INTERVAL = cfg['interval']
def main():
  global err_col_runner
  write_log_every = 50
  write_log_counter = 0
  running_in_error_mode = False
  while RUNNING:
    run_started_at = time.time()

    if last_update + timeout_s < run_started_at:
      if write_log_counter == 0:
        print("Apa102 timeout, running error color wheel")
        write_log_counter = write_log_every
      write_log_counter -= 1

      c_err_col = error_colors[err_col_runner]
      err_col_runner += 1
      if err_col_runner == nr_err_col:
        err_col_runner = 0
      DEBUG and print("setColor", c_err_col, str2hexColor(c_err_col))
      setAllColor(c_err_col)
      running_in_error_mode = True
    else:
      if running_in_error_mode == True:
        print("Apa102 timeout over")
        running_in_error_mode = False

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
  print("main thread finished")

sub=threading.Thread(target=subscribing)
pub=threading.Thread(target=main)

call ("/usr/local/bin/spidev_test -N", shell=True) #disable SPI0-CS

### Start MAIN ###

sub.start()
pub.start()
sub.join()
pub.join()

print("started threads")

n.notify("READY=1") #optional after initializing
n.notify("WATCHDOG=1")
