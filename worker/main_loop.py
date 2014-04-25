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
import worker
from worker.ws import EucaISConnection
from worker.imaging_task import ImagingTask


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
        worker.log.debug('main loop running with instance_id=%s' % (self.__instance_id))

    def start(self):
        # check if workflow enabled
        """
        if subprocess.call(['/usr/libexec/eucalyptus/euca-run-workflow', '-h'], stdout=os.devnull, stderr=os.devnull) != 0:
            worker.log.error('Failed to find euca-run-workflow. Would not start service')
            self.__status = WorkerLoop.STOPPED
        else:
            self.__status = WorkerLoop.RUNNING
        """
        self.__status = WorkerLoop.RUNNING
        while self.__status == WorkerLoop.RUNNING:
            worker.log.info('Querying for new imaging task')
            try:
                con = worker.ws.connect_imaging_worker(aws_access_key_id=config.get_access_key_id(),
                                                       aws_secret_access_key=config.get_secret_access_key(),
                                                       security_token=config.get_security_token())
                import_task = con.get_import_task()
                try:
                    task = ImagingTask.from_import_task(import_task)
                    if task:
                        worker.log.info('Processing import task %s' % task)
                        if task.process_task():
                            worker.log.info('Done processing task %s' % task.task_id)
                        else:
                            worker.log.warn('Processing of the task %s failed' % task.task_id)
                    else:
                        pass
                except Exception, err:
                    con.put_import_task_status(task_id=import_task.task_id, status='FAILED')
                    worker.log.error('Failed to process task for unknown reason: %s' % err)
            except Exception, err:
                tb = traceback.format_exc()
                worker.log.error(str(tb) +
                                 '\nFailed to query imaging service: %s' % err)
            query_period = config.QUERY_PERIOD_SEC
            while query_period > 0 and self.__status == WorkerLoop.RUNNING:
                time.sleep(1)
                query_period -= 1

        worker.log.info('Exiting')
        self.__status = WorkerLoop.STOPPED

    def stop(self):
        self.__status = WorkerLoop.STOPPING

    def status(self):
        return self.__status
