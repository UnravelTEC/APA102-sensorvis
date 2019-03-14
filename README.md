# APA102-sensorvis
Displays sensor data (e.g. CO2 levels) on APA102 RGB LED-Strips

Based on https://github.com/tinue/APA102_Pi

## Notes on APA102 

The Raspberry Pi is a 3.3 Volt device, and the APA102 LEDs are 5 Volt devices. Therefore it's possible that the 3.3 Volt SPI signal is not being recognized by the LED driver chips. To avoid this risk, use a 74AHCT125 or 74AHC125 level shifter for both the clock and the MOSI signal. You will not damage the Raspberry Pi if you don't use a level shifter, because the Raspberry Pi determines the voltage of MOSI and SCLK.

The LED strip uses a lot of power (roughly 20mA per LED, i.e. 60mA for one bright white dot). If you try to power the LEDs from the Raspberry Pi 5V output, you will most likely immediately kill the Raspberry! Therefore I recommend not to connect the power line of the LED with the Raspberry. To be on the safe side, use a separate USB power supply for the Raspberry, and a strong 5V supply for the LEDs. If you use a level shifter, power it from the 5V power supply as well.

## Connection

When driving more than a few LEDs, use a strong 5V Power supply!

- connect LED ground to one of the Raspberry ground pins
- connect LEDs to 5V (either Raspberry or external)
- Raspberry SPI MOSI -> Level Shifter -> LED Data
- Raspberry SPI SCLK -> LED Clock to 

SPI MISO (they don't talk back) and Chip Select (APA102 are always on) are not used.

## Software preparations

- Activate SPI
- Install Python 3 and some packages required by the Adafruit library: `aptitude install python3-dev python3-pip python3-smbus python3-rpi.gpio`
- Fetch the Adafruit_Python_GPIO library: `cd /tmp && wget https://github.com/adafruit/Adafruit_Python_GPIO/archive/master.zip && unzip master.zip`
- Install the library: `cd Adafruit_Python_GPIO-master && sudo python3 ./setup.py install`


