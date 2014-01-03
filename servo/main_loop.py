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
import servo
from servo.ws import EucaISConnection


class ServoLoop(object):
    STOPPED = "stopped"
    STOPPING = "stopping"
    RUNNING = "running"

    def __init__(self):
        # get the instance id from metadata service
        self.__instance_id = None
        self.__euca_host = config.get_clc_host()
        if self.__instance_id is None:
            self.__instance_id = config.get_servo_id()

        self.__status = ServoLoop.STOPPED
        servo.log.debug('main loop running with clc_host=%s, instance_id=%s' % (self.__euca_host, self.__instance_id))

    def start(self):
        self.__status = ServoLoop.RUNNING 
        while self.__status == ServoLoop.RUNNING:
            servo.log.info('querying CLC for new imaging task')
            try:
                access_key_id = config.get_access_key_id()
                secret_access_key = config.get_secret_access_key()
                security_token = config.get_security_token()
                con = EucaISConnection(host_name=self.__euca_host, aws_access_key_id=access_key_id,
                                       aws_secret_access_key=secret_access_key, security_token=security_token)
                task = con.get_import_task()
                if task != None:
                # task processing
                    servo.log.info('processing import task %s' % task.task_id)
                 
            except Exception, err:
                servo.log.error('failed to query the imaging service: %s' % err)

            start_time = time.time()
            while time.time() - start_time < config.QUERY_PERIOD_SEC and self.__status == ServoLoop.RUNNING:
                servo.log.debug('sleeping')
                time.sleep(10)

        self.__status = ServoLoop.STOPPED

    def stop(self):
        self.__status = ServoLoop.STOPPING

    def status(self):
        return self.__status
