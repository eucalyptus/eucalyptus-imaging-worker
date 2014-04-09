# Copyright 2009-2014 Eucalyptus Systems, Inc.
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
# Order matters here. We want to make sure we initialize logging before anything
# else happens. We need to initialize the logger that boto will be using.
#
from worker.logutil import log, set_loglevel
from worker.config import set_pidfile, set_boto_config
from worker.main_loop import WorkerLoop
import worker.config as config
import worker
import os
import subprocess
import sys
import re


__version__ = '1.0.0-dev'
Version = __version__


def get_block_devices():
    ret_list = []
    for filename in os.listdir('/dev'):
        if any(filename.startswith(prefix) for prefix in ('sd', 'xvd', 'vd', 'xd')):
            filename = re.sub('\d', '', filename)
            if not '/dev/'+filename in ret_list:
                ret_list.append('/dev/' + filename)
    return ret_list


def run_as_sudo(cmd):
    return subprocess.call('sudo %s' % cmd, shell=True)


def start_worker():
    if run_as_sudo('modprobe floppy > /dev/null') != 0:
        log.error('failed to load floppy driver')
    try:
        res = get_block_devices()
        res.sort(reverse=True)
        last_dev = res[0]
        worker.config.get_worker_id()
        if subprocess.call('ls -la %s > /dev/null' % last_dev, shell=True) != 0 or subprocess.call(
                'ls -la /mnt > /dev/null', shell=True) != 0:
            log.error('failed to find %s or /mnt' % last_dev)
        else:
            if run_as_sudo('mount | grep /mnt > /dev/null') == 1:
                if run_as_sudo('mkfs.ext3 %s 2>> /tmp/init.log' % last_dev) != 0 or run_as_sudo(
                                'mount %s /mnt 2>> /tmp/init.log' % last_dev) != 0:
                    log.error('failed to format and mount %s ' % last_dev)
                else:
                    log.info('%s was successfully formatted and mounted to /mnt' % last_dev)
                    if run_as_sudo('mkdir /mnt/imaging %s 2>> /tmp/init.log') != 0 or run_as_sudo(
                            'chown imaging-worker:imaging-worker /mnt/imaging 2>> /tmp/init.log') != 0:
                        log.error('could not create /mnt/imaging')
            else:
                log.info('%s is alredy mounted to /mnt' % last_dev)
    except Exception, err:
        log.error("Can't detect VM's id or set up worker due to %s", err)
        sys.exit(1)
    WorkerLoop().start()
