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
# Simple script to install the servo worker without using a package manager

# Install python code
python setup.py install

# Setup servo user
useradd -s /sbin/nologin -d /var/lib/eucalyptus-imaging-worker -M imaging-worker
install -v -m 0440 scripts/imaging-worker-sudo.conf /etc/sudoers.d/imaging-worker

# Setup needed for servo worker
install -v -m 755 scripts/imaging-worker-init /etc/init.d/eucalyptus-imaging-worker
sed -i 's/LOGLEVEL=info/LOGLEVEL=debug/' /etc/init.d/eucalyptus-imaging-worker
# Use set gid for imaging-worker owned directories
mkdir -p /var/{run,lib,log}/eucalyptus-imaging-worker
install -v -m 6700 -o imaging-worker -g imaging-worker -d /var/{run,lib,log}/eucalyptus-imaging-worker
chown imaging-worker:imaging-worker -R /etc/eucalyptus-imaging-worker
chmod 700 /etc/eucalyptus-imaging-worker

# NTP cronjob
install -p -m 755 -D scripts/worker-ntp-update /usr/libexec/eucalyptus-imaging-worker/ntp-update
install -p -m 755 -D scripts/worker-dns-update /usr/libexec/eucalyptus-imaging-worker/dns-update
install -p -m 0750 -D scripts/imaging-worker.cron /etc/cron.d/imaging-worker
chmod 0640 /etc/cron.d/imaging-worker
