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
import os
import string
import config
import worker
import subprocess
import httplib2
from lxml import objectify
from worker.ws import EucaEC2Connection
from worker.ws import EucaISConnection

class ImagingTask(object):
    FAILED_STATE  = 'FAILED'
    DONE_STATE  = 'DONE'
    EXTANT_STATE = 'EXTANT'

    def __init__(self, task_id, manifest_url=None, volume_id=None):
        self.task_id = task_id
        self.manifest_url = manifest_url
        self.volume_id = volume_id

    def __str__(self):
        return 'Task: {0}, manifest url: {1}, volume id: {2}'.format(self.task_id, self.manifest_url,
                self.volume_id)

    def get_block_devices(self):
        retlist=[]
        for filename in os.listdir('/dev'):
            if any(filename.startswith(prefix) for prefix in ('sd', 'xvd', 'vd', 'xd')):
                retlist.append('/dev/' + filename)
        return retlist

    def get_partition_size(self, partition):
        p = subprocess.Popen(["blockdev", "--getsize64", partition], stdout=subprocess.PIPE)
        return int(p.communicate()[0])        

    def get_manifest(self):
        if "imaging@" not in self.manifest_url:
            raise Exception('invalid manifest URL')
        resp, content = httplib2.Http().request(self.manifest_url.replace('imaging@', ''))
        if resp['status'] != '200' or len(content) <= 0:
            raise Exception('could not download the manifest file')
        root = objectify.XML(content)
        return root

    def next_device_name(self, all_dev):
        device = all_dev[0]
        lc = device[len(device)-1:]    
        if lc in string.digits:
            device = device[0:len(device)-1]
        lc = device[len(device)-1:]
        return device[0:len(device)-1] + chr(ord(lc)+1)

    def attach_volume(self, timeout_sec=300):
        if self.volume_id == None:
            raise RuntimeError('This import does not have a volume')
        timeout_time = time.time() + timeout_sec
        devices_before = self.get_block_devices()
        device_name = self.next_device_name(devices_before)
        instance_id = config.get_worker_id()

        ec2 = EucaEC2Connection(host_name=config.get_clc_host(),
                          aws_access_key_id=config.get_access_key_id(),
                          aws_secret_access_key=config.get_secret_access_key(),
                          port=config.get_clc_port(), 
                          path=config.get_ec2_path())
        worker.log.debug('attaching volume {0} to {1} as {2}'.format(self.volume_id, instance_id, device_name))
        if not ec2.attach_volume(self.volume_id, instance_id, device_name):
            raise RuntimeError('Can not attach volume {0} to the instance {1}'.format(
                              self.volume_id, instance_id)) #todo: add specific error?
        # wait till we have a new device
        while time.time() < timeout_time and len(devices_before)==len(self.get_block_devices()):
            worker.log.debug('waiting volume attachment')
            time.sleep(10)

        new_block_devices = self.get_block_devices()
        if len(devices_before)==len(new_block_devices):
            raise RuntimeError('Volume was not attached in {0} seconds'.format(timeout_sec)) #todo: add specific error?

        new_device_name = new_block_devices[0] # can it be different from device_name?
        return new_device_name

    def download_data(self, manifest_url, device_name):
        #todo: get location from config
        path_to_download_image = '/tmp/eucatoolkit/stages/downloadimage.py'
        manifest = manifest_url.replace('imaging@', '')
        worker.log.debug('Calling python %s -m %s -d %s' % (path_to_download_image, manifest, device_name))
        try:
            return subprocess.call(['python', path_to_download_image, '-m', manifest, '-d', device_name])
        except Exception, err:
            worker.log.error('Could not download data from object storage: %s' % err)
            return 1

    def detach_volume(self, timeout_sec=300):
        if self.volume_id == None:
            raise RuntimeError('This import does not have volume id')
        timeout_time = time.time() + timeout_sec
        ec2 = EucaEC2Connection(host_name=config.get_clc_host(),
                          aws_access_key_id=config.get_access_key_id(),
                          aws_secret_access_key=config.get_secret_access_key(),
                          port=config.get_clc_port(), 
                          path=config.get_ec2_path())
        worker.log.debug('detaching volume {0}'.format(self.volume_id))
        devices_before = self.get_block_devices()
        if not ec2.detach_volume(self.volume_id):
            raise RuntimeError('Can not dettach volume {0}'.format(self.volume_id)) #todo: add specific error?

        # wait till we have less devices
        while time.time() < timeout_time and len(devices_before)==len(self.get_block_devices()):
            worker.log.debug('waiting volume detachment')
            time.sleep(10)

        if len(devices_before)==len(self.get_block_devices()):
            raise RuntimeError('Volume was not dettached in {0} seconds'.format(timeout_sec)) #todo: add specific error?
        return True

    def process_task(self):
        is_conn = EucaISConnection(host_name=config.get_clc_host(),
                          aws_access_key_id=config.get_access_key_id(),
                          aws_secret_access_key=config.get_secret_access_key(),
                          port=config.get_clc_port(),
                          path=config.get_imaging_path())
        try:
            done_with_errors = True
            device_to_use = None
            manifest = self.get_manifest()
            image_size = int(manifest.image.size)
            if self.volume_id != None:
                worker.log.info('Attaching volume %s' % self.volume_id)  
                device_to_use = self.attach_volume()
                device_size = self.get_partition_size(device_to_use)
                worker.log.debug('Attached device size is %d bytes' % device_size)
                worker.log.debug('Needed for image/volume %d bytes' % image_size)
                if image_size > device_size:
                    worker.log.error('Device is too small for the image/volume')
                    is_conn.put_import_task_status(self.task_id, ImagingTask.FAILED_STATE, self.volume_id, 0)
                    self.detach_volume()
                    return False
                # download image to the block device
                if self.download_data(self.manifest_url, device_to_use) == 0:
                    done_with_errors = False
            else:
                worker.log.info('There is no volume id. Importing to Object Storage')
                raise RuntimeError('Import to Object Storage is not supported')
            # detaching volume
            if device_to_use != None:
                 worker.log.info('Detaching volume %s' % self.volume_id)
                 self.detach_volume()
            # set done or error state
            if done_with_errors:
                is_conn.put_import_task_status(self.task_id, ImagingTask.FAILED_STATE, self.volume_id)
                return False
            else:
                is_conn.put_import_task_status(self.task_id, ImagingTask.DONE_STATE, self.volume_id, image_size)
                return True
        except Exception, err:
            worker.log.error('Failed to process task: %s' % err)
