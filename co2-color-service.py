#!/usr/bin/env python3

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

valuefile = '/run/sensors/scd30/last'

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

    def cleanup(self, strip):
        """Cleanup method."""
        self.shutdown(strip, self.num_led)
        strip.clear_strip()
        strip.cleanup()

    def setAll(self, strip, color):
      # print(color)
      for i in range(0,self.num_led):
        strip.set_pixel_rgb(i, color, 20)
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
            strip = apa102.APA102(num_led=self.num_led,
                                  global_brightness=self.global_brightness,
                                  mosi = self.mosi, sclk = self.sclk,
                                  order=self.order) # Initialize the strip
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
              if ftime + 2 < now:
                print('valuefile older than 2s')
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
                    if(value < 800):
                      self.setAll(strip, 0x00FF00)
                    elif(value < 1500):
                      self.setAll(strip, 0xFFAA00)
                    else:
                      self.setAll(strip, 0xFF0000)
                if value == 999999:
                  print('valuefile empty')
                  self.setAll(strip, 0x0000FF)

#                    print(value)

              time.sleep(1)

        except KeyboardInterrupt:  # Ctrl-C can halt the light program
            print('Interrupted...')
            self.cleanup(strip)

myclass = Simple(num_led=74, pause_value=3, num_steps_per_cycle=1, num_cycles=1)
myclass.start()

signal.signal(signal.SIGINT, myclass.cleanup)
signal.signal(signal.SIGTERM, myclass.cleanup)

