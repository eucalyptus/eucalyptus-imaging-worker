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
import time
import config
import os
import subprocess
import traceback
import eucaimgworker
from eucaimgworker import LOGGER_NAME
from eucaimgworker.logutil import CustomLog
from eucaimgworker.ws import EucaISConnection
from eucaimgworker.imaging_task import ImagingTask
from eucaimgworker.failure_with_code import FailureWithCode
from eucaimgworker.utils import run_as_sudo, get_block_devices
from task_exit_codes import *

logger = CustomLog(LOGGER_NAME)

def spin_locks():
    try:
        while not (os.path.exists("/var/lib/eucalyptus-imaging-worker/ntp.lock")):
            time.sleep(2)
            logger.debug('waiting on ntp setup (reboot if continued)')
        os.remove("/var/lib/eucalyptus-imaging-worker/ntp.lock")
    except Exception, err:
        logger.error('failed to spin on locks: %s' % err)


def start_worker():
    spin_locks()
    if run_as_sudo('modprobe floppy > /dev/null') != 0:
        logger.error('failed to load floppy driver')
    try:
        res = get_block_devices()
        if len(res) != 2:
            logger.error(
                "Found %d block device(s). Imaging VM (re)started in a very small type or with volume(s) attached" % len(
                    res))
            sys.exit(1)
        res.sort(reverse=True)
        last_dev = res[0]
        eucaimgworker.config.get_worker_id()
        if subprocess.call('ls -la %s > /dev/null' % last_dev, shell=True) != 0 or subprocess.call(
                'ls -la /mnt > /dev/null', shell=True) != 0:
            logger.error('failed to find %s or /mnt' % last_dev)
        else:
            if run_as_sudo('mount %s /mnt 2>> /tmp/init.log' % last_dev) == 0:
                if run_as_sudo('mkfs.ext3 -F %s 2>> /tmp/init.log' % last_dev) != 0 or run_as_sudo(
                                'mount %s /mnt 2>> /tmp/init.log' % last_dev) != 0:
                    logger.error('failed to format and mount %s ' % last_dev)
                else:
                    log.info('%s was successfully formatted and mounted to /mnt' % last_dev)
                    if run_as_sudo('mkdir /mnt/imaging %s 2>> /tmp/init.log') != 0 or run_as_sudo(
                            'chown imaging-worker:imaging-worker /mnt/imaging 2>> /tmp/init.log') != 0:
                        logger.error('could not create /mnt/imaging')
            else:
                # make sure that /mnt/imaging exist and re-create it if needed
                if subprocess.call('ls -la /mnt/imaging > /dev/null', shell=True) != 0:
                    if run_as_sudo('mkdir /mnt/imaging %s 2>> /tmp/init.log') != 0 or run_as_sudo(
                            'chown imaging-worker:imaging-worker /mnt/imaging 2>> /tmp/init.log') != 0:
                        logger.error('could not create /mnt/imaging')
    except Exception, err:
        logger.error("Can't detect VM's id or set up worker due to %s", err)
        sys.exit(1)
    WorkerLoop().start()

class WorkerLoop(object):
    STOPPED = "stopped"
    STOPPING = "stopping"
    RUNNING = "running"

    def __init__(self):
        # get the instance id from metadata service
        self.__instance_id = None
        if self.__instance_id is None:
            self.__instance_id = config.get_worker_id()

        self.__status = WorkerLoop.STOPPED
        logger.debug('main loop running with instance_id=%s' % (self.__instance_id))

    def start(self):
        self.__status = WorkerLoop.RUNNING
        while self.__status == WorkerLoop.RUNNING:
            logger.info('Querying for new imaging task')
            try:
                con = eucaimgworker.ws.connect_imaging_worker(aws_access_key_id=config.get_access_key_id(),
                                                       aws_secret_access_key=config.get_secret_access_key(),
                                                       security_token=config.get_security_token())
                import_task = con.get_import_task()
                try:
                    task = ImagingTask.from_import_task(import_task)
                    if task:
                        logger.info('Processing import task %s' % task, task.task_id)
                        if task.process_task():
                            logger.info('Done processing task %s' % task.task_id, task.task_id)
                        else:
                            logger.error('Processing of the task %s failed' % task.task_id, task.task_id)
                    else:
                        pass
                except Exception, err:
                    if type(err) is FailureWithCode:
                        con.put_import_task_status(task_id=import_task.task_id, status='FAILED',
                                                   error_code=err.failure_code)
                    else:
                        con.put_import_task_status(task_id=import_task.task_id, status='FAILED',
                                                   error_code=GENERAL_FAILURE)
                        logger.error('Failed to process task for unknown reason: %s' % err)
            except Exception, err:
                tb = traceback.format_exc()
                logger.error(str(tb) +
                                 '\nFailed to query imaging service: %s' % err)
            query_period = config.QUERY_PERIOD_SEC
            while query_period > 0 and self.__status == WorkerLoop.RUNNING:
                time.sleep(1)
                query_period -= 1

        logger.info('Exiting')
        self.__status = WorkerLoop.STOPPED

    def stop(self):
        self.__status = WorkerLoop.STOPPING

    def status(self):
        return self.__status
