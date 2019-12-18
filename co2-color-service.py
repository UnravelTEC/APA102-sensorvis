#!/usr/bin/python3

# based on https://github.com/tinue/APA102_Pi, © tinue et.al.
#
# our version by Michael Maier <michael.maier@unraveltec.com>
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


"""The module contains templates for colour cycles"""
import time
from driver import apa102
import re
import signal,os
import math

valuefile = '/run/sensors/scd30/last'

brightness = 10 # Percent
timeout_s = 7
timeout_s = 5

class Simple:
        
    def __init__(self, num_led, pause_value = 0, num_steps_per_cycle = 100,
                 num_cycles = -1, global_brightness = 255, order = 'rgb',
                 mosi = 10, sclk = 11):
        self.num_led = num_led # The number of LEDs in the strip
        self.pause_value = pause_value # How long to pause between two runs
        self.num_steps_per_cycle = num_steps_per_cycle # Steps in one cycle.
        self.num_cycles = num_cycles # How many times will the program run
        self.global_brightness = global_brightness # Brightness of the strip
        self.order = order # Strip colour ordering
        self.mosi = mosi # Master out slave in of the SPI protocol
        self.sclk = sclk # Clock line of the SPI protocol
        self.strip = apa102.APA102(num_led=self.num_led,
                              global_brightness=self.global_brightness,
                              mosi = self.mosi, sclk = self.sclk,
                              order=self.order) # Initialize the strip

    def init(self, strip, num_led):
        """This method is called to initialize a color program.

        The default does nothing. A particular subclass could setup
        variables, or even light the strip in an initial color.
        """
        pass

    def shutdown(self, strip, num_led):
        """This method is called before exiting.

        The default does nothing
        """
        pass

    def cleanup(self):
        """Cleanup method."""
        self.shutdown(self.strip, self.num_led)
        self.strip.clear_strip()
        self.strip.cleanup()

    def setAll(self, strip, color):
      # print(color)
      for i in range(0,self.num_led):
        strip.set_pixel_rgb(i, color, brightness)
      strip.show()

    def setToLevel(self, strip, value):
      maxled = self.num_led
      green = 0x00FF00
      yellow = 0xFFAA00
      orange = 0xFF3300
      red = 0xFF0000

      # green: 0-800
      # yellow: 800-1500
      # red: 1500-2500 (2500 == end of strip)
      green_begin = 300
      yellow_threshold = 800
      orange_threshold = 1500
      red_threshold = 2500
      max_value = 3500

      num_static = 8

      # set first ones according to value
      for i in range(0, num_static):
        if value < yellow_threshold:
          strip.set_pixel_rgb(i, green, brightness)
        elif value < orange_threshold:
          strip.set_pixel_rgb(i, yellow, brightness)
        elif value < red_threshold:
          strip.set_pixel_rgb(i, orange, brightness)
        else: 
          strip.set_pixel_rgb(i, red, brightness)

      if value > max_value: # cap at max
        value = max_value

      how_many_leds_lit = math.ceil(value / max_value * maxled)
      yellow_led_start = math.ceil(yellow_threshold / max_value * maxled)
      orange_led_start = math.ceil(orange_threshold / max_value * maxled)
      red_led_start = math.ceil(red_threshold / max_value * maxled)

      #print(how_many_leds_lit)

      for i in range(num_static, how_many_leds_lit):
        if i < yellow_led_start:
          strip.set_pixel_rgb(i, green, brightness)
        elif i < orange_led_start:
          strip.set_pixel_rgb(i, yellow, brightness)
        elif i < red_led_start:
          strip.set_pixel_rgb(i, orange, brightness)
        else:
          strip.set_pixel_rgb(i, red, brightness)
      for i in range(how_many_leds_lit, maxled):
        strip.set_pixel_rgb(i,0x000000, 0)

      strip.show()

    def rotate(self,strip):
      self.setAll(strip,0xFF0000)
      time.sleep(0.3)
      self.setAll(strip,0x00FF00)
      time.sleep(0.3)
      self.setAll(strip,0x0000FF)
      time.sleep(0.3)

    def start(self):
        """This method does the actual work."""
        try:
            strip = self.strip
            strip.clear_strip()
            self.init(strip, self.num_led) # Call the subclasses init method
            strip.show()
            current_cycle = 0

            while True:  # Loop forever
              if not os.path.isfile(valuefile):
                self.rotate(strip)
                continue

              now = time.time()
              ftime = os.path.getmtime(valuefile)
              if ftime + timeout_s < now:
                print('valuefile older than ' + str(timeout_s) + 's')
                self.setAll(strip, 0x0000FF)
                time.sleep(1)
                continue

              with open(valuefile, 'r') as content_file:
                content = content_file.read()
                dataarray = content.splitlines()
                value = 999999
                for i in dataarray:
                  if re.search(r'gas="CO2"', i):
                    value = float(i.split()[1])
                    self.setToLevel(strip, value)
                    """
                    if(value < 800):
                      self.setAll(strip, 0x00FF00)
                    elif(value < 1500):
                      self.setAll(strip, 0xFFAA00)
                    else:
                      self.setAll(strip, 0xFF0000)
                    """
                if value == 999999:
                  print('valuefile empty')
                  self.setAll(strip, 0x0000FF)

#                    print(value)

              time.sleep(0.1)

        except KeyboardInterrupt:  # Ctrl-C can halt the light program
            print('Interrupted...')
            self.cleanup(strip)

myclass = Simple(num_led=74, pause_value=3, num_steps_per_cycle=1, num_cycles=1)

def functionCleanup(a,b):
  myclass.cleanup()
  # FIXME on kill or C-C, GPIO-1.0.3-py3.5.egg/Adafruit_GPIO/SPI.py", line 83 throws "[Errno 9] Bad file descriptor", but it doesn't matter.

signal.signal(signal.SIGINT, functionCleanup)
signal.signal(signal.SIGTERM, functionCleanup)

myclass.start()
