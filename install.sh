#!/bin/bash
# installs services etc for coloring LED strips to sensor values

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

targetdir=/usr/local/bin/

if [ ! "$1" ]; then
  aptitude update
  aptitude install -y python3-dev python3-pip python3-smbus python3-rpi.gpio python3-setuptools

  (
    cd /tmp
    wget https://github.com/adafruit/Adafruit_Python_GPIO/archive/master.zip
    unzip master.zip
    cd Adafruit_Python_GPIO-master
    python3 ./setup.py install
  )
  mkdir -p $targetdir 
fi

(
  cd /usr/local/
  if [ ! "$(find . -iname apa102.py)" ]; then
    pip3 install --upgrade .
  fi
)

exe1=co2-color-service.py
serv1=co2-color.service

rsync -raxc --info=name $exe1 $targetdir

rsync -raxc --info=name $serv1 /etc/systemd/system/

systemctl enable $serv1 && echo "systemctl enable $serv1 OK"
systemctl restart $serv1 && echo "systemctl restart $serv1 OK"

echo "\nDon't forget to enable SPI!"
