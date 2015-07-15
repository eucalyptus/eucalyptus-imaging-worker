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
import boto
import httplib
import boto.utils
from boto.ec2.regioninfo import RegionInfo
from boto.ec2.connection import EC2Connection
from boto.iam.connection import IAMConnection
from worker.ssl.server_cert import ServerCertificate
from worker.ws.instance_import_task import InstanceImportTask
import time
import M2Crypto
from defusedxml.ElementTree import fromstring
import worker
import worker.config as config
from worker.task_exit_codes import *
from worker.failure_with_code import FailureWithCode

def connect_imaging_worker(host_name=config.get_imaging_service_url(), port=8773, path="services/Imaging", aws_access_key_id=None,
                           aws_secret_access_key=None, security_token=None, **kwargs):
    return EucaISConnection(host_name=host_name, port=port, path=path, aws_access_key_id=aws_access_key_id,
                            aws_secret_access_key=aws_secret_access_key, security_token=security_token,
                            **kwargs)


def connect_ec2(host_name=config.get_compute_service_url(), port=8773, path="services/Eucalyptus", aws_access_key_id=None,
                aws_secret_access_key=None, security_token=None, **kwargs):
    return EucaEC2Connection(host_name=host_name, port=port, path=path, aws_access_key_id=aws_access_key_id,
                             aws_secret_access_key=aws_secret_access_key, security_token=security_token,
                             **kwargs)


class EucaEC2Connection(object):
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 host_name=None, is_secure=False, path='services/Eucalyptus',
                 security_token=None, validate_certs=False, port=8773):
        region = RegionInfo(name='eucalyptus', endpoint=host_name)
        self.conn = EC2Connection(region=region, host=host_name, aws_access_key_id=aws_access_key_id,
                                  aws_secret_access_key=aws_secret_access_key, port=port,
                                  path=path, security_token=security_token, is_secure=is_secure,
                                  validate_certs=validate_certs)
        self.conn.APIVersion = '2013-08-15'  #TODO: set new version?
        self.conn.http_connection_kwargs['timeout'] = 30

    def attach_volume(self, volume_id, instance_id, device_name):
        return self.conn.attach_volume(volume_id, instance_id, device_name)

    def detach_volume(self, volume_id):
        return self.conn.detach_volume(volume_id)

    def describe_volumes(self, volume_ids=None):
        return self.conn.get_all_volumes(volume_ids)

    def describe_volume(self, volume_id=None):
        if volume_id == None:
            raise RuntimeError("There is no volume_id provoded")
        vols = self.describe_volumes([volume_id, 'verbose'])
        for vol in vols:
            if vol.id == volume_id:
                break
        if not vol or vol.id != volume_id:
            raise RuntimeError('Failed to lookup volume:"{0}" from system'
                               .format(volume_id))
        return vol

    def detach_volume_and_wait(self, volume_id, timeout_sec=3000, task_id=None):
        '''
        Attempts to detach a volume, and wait for the volume's status
        to become 'available'. Will raise RunTimeError upon failure.
        :param volume_id: string representing volume id. ie: vol-abcd1234
        :param timeout_sec: Timeout to wait for volume to detach in seconds
        '''
        vol = None
        vol = self.describe_volume(volume_id)
        attachment_state = vol.attachment_state()
        if attachment_state and attachment_state != 'detaching':
            vol.detach()
        start = time.time()
        elapsed = 0
        while elapsed < timeout_sec:
            vol = self.describe_volume(volume_id)
            if vol.status == 'available' or vol.status.startswith('delet'):
                worker.log.debug('detach_volume_and_wait volume status: "%s"' % vol.status, process=task_id)
                return
            time.sleep(5)
            elapsed = time.time() - start
        # Volume has failed to detach within the given timeout raise error
        instance = 'unknown'
        if hasattr(vol, "attach_data"):
            instance = str(vol.attach_data.instance_id)
        raise FailureWithCode('Volume:"{0}" failed to detach from:"{1}". '
                           'Status:"{2}", elapsed: {3}/{4}'
                           .format(vol.id, instance, vol.status, elapsed, timeout_sec), DETACH_VOLUME_FAILURE)

    def attach_volume_and_wait(self,
                               volume_id,
                               instance_id,
                               device_name,
                               poll_interval=5,
                               timeout_sec=300):
        '''
        Attempts to attach a volume and wait for the correct attached status.

        '''
        vol = None
        vol = self.describe_volume(volume_id)
        # Attempt to attach
        vol.attach(instance_id=instance_id, device=device_name)
        # Monitor attached state to attached or failure
        start = time.time()
        vol = self.describe_volume(volume_id)
        while vol.attachment_state() != 'attached':
            time.sleep(poll_interval)
            elapsed = time.time() - start
            # Catch failure states and raise error
            if elapsed > timeout_sec or \
                vol.status == 'available' or \
                    vol.status.startswith('delet'):
                raise FailureWithCode('Failed to attach volume:"{0}" '
                                   'to attach to:"{1}". Status:"{2}". '
                                   'Elapsed:"{3}/{4}"'.format(volume_id,
                                                          instance_id,
                                                          vol.status,
                                                          elapsed,
                                                          timeout_sec), ATTACH_VOLUME_FAILURE)
            time.sleep(poll_interval)
            vol = self.describe_volume(volume_id)
        # Final check for correct volume attachment
        attached_id = vol.attach_data.instance_id
        if attached_id != instance_id:
            raise FailureWithCode('Volume:"{0}" not attached to correct '
                               'instance:"{1}". Status:"{2}". Attached:"{3}".'
                               'Elapsed:"{4}/{5}"'.format(volume_id,
                                                          instance_id,
                                                          vol.status,
                                                          attached_id,
                                                          elapsed,
                                                          timeout_sec), ATTACH_VOLUME_FAILURE)


class EucaISConnection(object):
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 host_name=None, is_secure=False, path='services/Imaging',
                 security_token=None, validate_certs=False, port=8773):
        region = RegionInfo(name='eucalyptus', endpoint=host_name)
        self.conn = EC2Connection(region=region, host=host_name, aws_access_key_id=aws_access_key_id,
                                  aws_secret_access_key=aws_secret_access_key, port=port,
                                  path=path, security_token=security_token, is_secure=is_secure,
                                  validate_certs=validate_certs)
        self.conn.APIVersion = '2014-02-14'  #TODO: set new version?
        self.conn.http_connection_kwargs['timeout'] = 30

    def get_import_task(self):
        params = {'InstanceId': config.get_worker_id()}
        task = self.conn.get_object('GetInstanceImportTask', params, InstanceImportTask, verb='POST')
        if not task or not task.task_id:
            return None
        else:
            return task

    """
    Communicates conversion status to the server
    Returns False if task should be canceled
    """

    def put_import_task_status(self, task_id=None, status=None, volume_id=None, bytes_converted=None, error_code=None,
                               message=None):
        if task_id is None or status is None:
            raise RuntimeError("Invalid parameters")
        params = {'InstanceId': config.get_worker_id(), 'ImportTaskId': task_id, 'Status': status}
        if bytes_converted is not None:
            params['BytesConverted'] = bytes_converted
        if volume_id is not None:
            params['VolumeId'] = volume_id
        if error_code is not None:
            params['ErrorCode'] = error_code
        if message is not None:
            params['Message'] = message
        resp = self.conn.make_request('PutInstanceImportTaskStatus', params, path='/', verb='POST')
        if resp.status != 200:
            raise httplib.HTTPException(resp.status, resp.reason, resp.read())
        response = resp.read()
        root = fromstring(response)
        cancelled = root.getchildren()[0] if len(root.getchildren()) == 1 else 'true'
        return 'true' != cancelled.text
