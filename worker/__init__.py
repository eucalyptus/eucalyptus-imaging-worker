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
from worker.logutil import CustomLog, set_loglevel, set_boto_loglevel, set_log_file_count, set_log_file_size
from worker.config import set_pidfile, set_boto_config
from worker.main_loop import WorkerLoop
import worker.config as config
import worker
import os
import subprocess
import sys
import re
import time

__version__ = '1.0.0-dev'
Version = __version__
log = CustomLog('worker')
workflow_log = CustomLog('euca-workflow')

def spin_locks():
    try:
        while not (os.path.exists("/var/lib/eucalyptus-imaging-worker/ntp.lock")):
            time.sleep(2)
            log.debug('waiting on ntp setup (reboot if continued)')
        os.remove("/var/lib/eucalyptus-imaging-worker/ntp.lock")
    except Exception, err:
        log.error('failed to spin on locks: %s' % err)


def get_block_devices():
    ret_list = []
    for filename in os.listdir('/dev'):
        if any(filename.startswith(prefix) for prefix in ('sd', 'xvd', 'vd', 'xd')):
            filename = re.sub('\d', '', filename)
            if not '/dev/' + filename in ret_list:
                ret_list.append('/dev/' + filename)
    return ret_list


def run_as_sudo(cmd):
    return subprocess.call('sudo %s' % cmd, shell=True)


def start_worker():
    spin_locks()
    if run_as_sudo('modprobe floppy > /dev/null') != 0:
        log.error('failed to load floppy driver')
    try:
        res = get_block_devices()
        if len(res) != 2:
            log.error(
                "Found %d block device(s). Imaging VM (re)started in a very small type or with volume(s) attached" % len(
                    res))
            sys.exit(1)
        res.sort(reverse=True)
        last_dev = res[0]
        worker.config.get_worker_id()
        if subprocess.call('ls -la %s > /dev/null' % last_dev, shell=True) != 0 or subprocess.call(
                'ls -la /mnt > /dev/null', shell=True) != 0:
            log.error('failed to find %s or /mnt' % last_dev)
        else:
            if run_as_sudo('mount %s /mnt 2>> /tmp/init.log' % last_dev) == 0:
                if run_as_sudo('mkfs.ext3 -F %s 2>> /tmp/init.log' % last_dev) != 0 or run_as_sudo(
                                'mount %s /mnt 2>> /tmp/init.log' % last_dev) != 0:
                    log.error('failed to format and mount %s ' % last_dev)
                else:
                    log.info('%s was successfully formatted and mounted to /mnt' % last_dev)
                    if run_as_sudo('mkdir /mnt/imaging %s 2>> /tmp/init.log') != 0 or run_as_sudo(
                            'chown imaging-worker:imaging-worker /mnt/imaging 2>> /tmp/init.log') != 0:
                        log.error('could not create /mnt/imaging')
            else:
                # make sure that /mnt/imaging exist and re-create it if needed
                if subprocess.call('ls -la /mnt/imaging > /dev/null', shell=True) != 0:
                    if run_as_sudo('mkdir /mnt/imaging %s 2>> /tmp/init.log') != 0 or run_as_sudo(
                            'chown imaging-worker:imaging-worker /mnt/imaging 2>> /tmp/init.log') != 0:
                        log.error('could not create /mnt/imaging')
    except Exception, err:
        log.error("Can't detect VM's id or set up worker due to %s", err)
        sys.exit(1)
    WorkerLoop().start()
