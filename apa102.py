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
import sys
import os, signal
# from subprocess import call
import spidev

from math import ceil

from copy import deepcopy

n.notify("WATCHDOG=1")

def eprint(*args, **kwargs):
  print(*args, file=sys.stderr, **kwargs)
  sys.stderr.flush()

name = "APA102" # Uppercase
cfg = {
    "interval": 0.3,
    "bus": 0,
    "address": 0,
    "busfreq": 400000,
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
      },
    "valuefile": '/run/sensors/scd30/last'
    }

n.notify("WATCHDOG=1")
DEBUG = False

fcfg = deepcopy(cfg) # final config used
if os.path.isfile(cfg['configfile']) and os.access(cfg['configfile'], os.R_OK):
  with open(cfg['configfile'], 'r') as ymlfile:
    import yaml
    filecfg = yaml.load(ymlfile)
    print("opened configfile", cfg['configfile'])
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


cfg = fcfg

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

if not 'thresholds' in cfg or not 'thresholds_single' in cfg:
  eprint('no thresholds in cfg, exit')
  exit(1)

tags = target['tags']
sensor = tags['sensor']
del tags['sensor'] # implied by topic, no need to store
measurement = target['measurement']
valuekey = target['value']

thresholds = cfg['thresholds']
thresholds_single = cfg['thresholds_single']

spi = spidev.SpiDev()
DEBUG and print('after spi declare')
spi.open(cfg['bus'], cfg['address'])
DEBUG and print('after spi open')
spi.max_speed_hz = cfg['busfreq']
DEBUG and print('after spi hz')
spi.mode = 1
DEBUG and print('after spi mode')
n.notify("WATCHDOG=1")

RUNNING = True
def exit_gracefully(a=False,b=False):
  global RUNNING
  print("exit gracefully...")
  RUNNING = False
  print("waiting for threads... ", end='')
  time.sleep(2)
  print("finishing")
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

def setPixel(lednr, red, green, blue, bright_percent=G_BN):
  bn_float = bright_percent / 100
  if lednr < 0 or lednr >= nleds:
    return
  ledstart = 0xFF # full global brightness
  start_index = 4 * lednr
  LED_ARR[start_index] = ledstart
  LED_ARR[start_index + 3] = ceil(red * bn_float) 
  LED_ARR[start_index + 2] = ceil(green * bn_float)
  LED_ARR[start_index + 1] = ceil(blue * bn_float)
  DEBUG and print(lednr, ":", hex(LED_ARR[start_index]) , hex(LED_ARR[start_index + 1]), hex(LED_ARR[start_index + 2]), hex(LED_ARR[start_index + 3]))

def show():
  spi.xfer([0] * 4) # clock_start_frame
  spi.xfer(list(LED_ARR)) # xfer2 kills the list, unfortunately. So it must be copied first
  spi.xfer([0xFF] * 4) # end frame
  # for _ in range((nleds + 15) // 16): # clock_end_frame

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
#  if DEBUG:
#    return(1 if  ((intcol & 0xFF0000) >> 16) > 0 else 0, 1 if ((intcol & 0x00FF00) >> 8) > 0 else 0, 1 if (intcol & 0x0000FF) > 0 else 0)
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
      setPixel(led,red,green,blue,G_BN)
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
    DEBUG and print("#", led, "fixed", strip_colors[led])

  print("strip with", nleds , "LEDs, ", fixed, "fixed.")
  for led in range(len(thresholds_single)):
    this_led_min_val = thresholds_single[led]
    colorstr = getColorFromThreshold(this_led_min_val)
    (red, green, blue) = str2hexColor(colorstr)
    strip_colors.append( (red, green, blue, G_BN) )
    DEBUG and print(fixed + led, strip_colors[fixed + led])

preCalcStrip()

def setBarLevel(value, brightness = G_BN):
  if value > max_value:
    value = max_value

  fixed = cfg['fixed']
  fixedcolorstr = getColorFromThreshold(value)
  (fixr, fixg, fixb) = str2hexColor(fixedcolorstr)
  for led in range(fixed):
    setPixel(led, fixr, fixg, fixb, brightness)
    DEBUG and print(led, (fixr, fixg, fixb, brightness))

  nr_led = fixed -1

  if 'ledcfg' in cfg:
    ledcfg = cfg['ledcfg']
    for step in ledcfg:
      nr_led = fixed -1
      if value > step['from']:
        DEBUG and print(step)
        led_a = step['leds']
        defined_leds = len(led_a)
        for led_i in led_a:
          nr_led += 1
          color = led_i['c']
          (red, green, blue) = str2hexColor(color)
          bn = led_i['bn'] if 'bn' in led_i else 1
          # todo calc bn by rgb/bn
          setPixel(nr_led, red, green, blue)
          DEBUG and print(nr_led, red, green, blue)
        for i in range(defined_leds+1, nleds):
          setPixel(i, 0,0,0,0)

    DEBUG and print("--------------------")
    show()
    return

  for led_threshold in thresholds_single:
    nr_led += 1
    DEBUG and print(nr_led, led_threshold)
    if value > led_threshold:
      cled = strip_colors[nr_led]
      setPixel(nr_led, cled[0], cled[1], cled[2], cled[3])
      DEBUG and print(nr_led, cled)
    else:
      setPixel(nr_led, 0,0,0,0)
      DEBUG and print(nr_led, 0,0,0,0)
  DEBUG and print("--------------------")

  show()


last_update = time.time()

error_colors = [ "red", "green", "blue" ]
nr_err_col = len(error_colors)
err_col_runner = 0

setAllColor("red")
time.sleep(0.33)
setAllColor("green")
time.sleep(0.33)
setAllColor("blue")
time.sleep(0.33)

vfile = cfg['valuefile']


n.notify("WATCHDOG=1")
MEAS_INTERVAL = cfg['interval']
def main():
  global err_col_runner, last_update
  lastmodtime = 0
  write_log_every = 50
  write_log_counter = 0
  running_in_error_mode = False
  while RUNNING:
    run_started_at = time.time()

    if os.path.isfile(vfile):
      currentmodtime = os.path.getmtime(vfile)
      if currentmodtime > lastmodtime:
        lastmodtime = currentmodtime
        current_file = open(vfile, 'r')
        for line in current_file:
          # print(line)
          line_array = line.split()
          if len(line_array) > 1:
            if len(line_array) == 2:
              metric = line_array[0]
              float_val = float(line_array[1])
            DEBUG and print(metric, float_val)
            if isinstance(float_val,float) and metric.startswith('gas_ppm'):
              setBarLevel(float_val)
              last_update = time.time()
              break
      else:
        DEBUG and print('wait for file update')

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

    # DEBUG and print("duration of run: {:10.4f}s.".format(run_duration))

    to_wait = MEAS_INTERVAL - run_duration
    if to_wait > 0:
      # DEBUG and print("wait for "+str(to_wait)+"s")
      time.sleep(to_wait - 0.002)
    else:
      DEBUG and print("no wait, {0:4f}ms over".format(- to_wait*1000))
  print("main thread finished")

main()

# call ("/usr/local/bin/spidev_test -N", shell=True) #disable SPI0-CS


n.notify("READY=1") #optional after initializing
n.notify("WATCHDOG=1")
