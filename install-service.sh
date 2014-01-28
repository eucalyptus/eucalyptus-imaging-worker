#!/bin/bash
#
# Copyright 2009-2013 Eucalyptus Systems, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#
# Please contact Eucalyptus Systems, Inc., 6755 Hollister Ave., Goleta
# CA 93117, USA or visit http://www.eucalyptus.com/licenses/ if you need
# additional information or have any questions.

#
# Simple script to install the servo service without using a package manager

# Install python code
python setup.py install

# Setup servo user
useradd -s /sbin/nologin -d /var/lib/eucalyptus-imaging-service -M imaging-service
install -v -m 0440 scripts/service-sudo.conf /etc/sudoers.d/imaging-service

# Setup needed for servo service
install -v -m 755 scripts/imaging-service-init /etc/init.d/eucalyptus-imaging-service
sed -i 's/LOGLEVEL=info/LOGLEVEL=debug/' /etc/init.d/eucalyptus-imaging-service
# Use set gid for imaging-service owned directories
install -v -m 6700 -o imaging-service -g imaging-service -d /var/{run,lib,log}/eucalyptus-imaging-service
chown imaging-service:imaging-service -R /etc/eucalyptus-imaging-service
chmod 700 /etc/eucalyptus-imaging-service

# NTP cronjob
install -p -m 755 -D scripts/service-ntp-update /usr/libexec/eucalyptus-imaging-service/service-ntp-update
install -p -m 0750 -D scripts/imaging-service.cron /etc/cron.d/imaging-service
