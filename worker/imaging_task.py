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
import json
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
    def __init__(self, task_id, task_type):
        self.task_id = task_id
        self.task_type = task_type 
        self.is_conn = worker.ws.connect_imaging_worker(host_name=config.get_clc_host(), aws_access_key_id=config.get_access_key_id(), 
                                             aws_secret_access_key=config.get_secret_access_key(), security_token=config.get_security_token())

    def get_task_id(self):
        return self.task_id

    def get_task_type(self):
        return self.task_type

    def process_task(self):
        raise Exception("Not implemented")

    def report_running(self, volume_id=None, bytes_transferred=None):
        return self.is_conn.put_import_task_status(self.task_id, ImagingTask.EXTANT_STATE, volume_id, bytes_transferred)
    
    def report_done(self, volume_id=None, bytes_transferred=None):
        self.is_conn.put_import_task_status(self.task_id, ImagingTask.DONE_STATE, volume_id, bytes_transferred)

    def report_failed(self, volume_id=None, bytes_transferred=None):
        self.is_conn.put_import_task_status(self.task_id, ImagingTask.FAILED_STATE, volume_id, bytes_transferred)

    """
    param: instance_import_task (object representing ImagingService's message)
    return: ImagingTask
    """
    @staticmethod
    def from_import_task(import_task):
        if not import_task:
            return None
        task = None
        if import_task.task_type == "import_volume" and import_task.volume_task:
            volume_id = import_task.volume_task.volume_id
            manifests = import_task.volume_task.image_manifests
            manifest_url = None
            if manifests and len(manifests) > 0:
                manifest_url = manifests[0].manifest_url
            task = VolumeImagingTask(import_task.task_id, manifest_url, volume_id)
        elif import_task.task_type == "convert_image" and import_task.instance_store_task:
            bucket = import_task.instance_store_task.bucket
            prefix = import_task.instance_store_task.prefix
            manifests = import_task.instance_store_task.image_manifests
            task = InstanceStoreImagingTask(import_task.task_id, bucket, prefix, manifests)
        return task

class InstanceStoreImagingTask(ImagingTask):
    def __init__(self, task_id, bucket=None, prefix=None, image_manifests=None):
        ImagingTask.__init__(self, task_id, "convert_image")
        # name of the bucket that converted image will be stored
        self.bucket = bucket
        # prefix of the image file (e.g., {prefix}.manifest.xml)
        self.prefix = prefix

        # list of image manifests that will be the sources of conversion
        # [{'manifest_url':'http://..../vmlinuz.manifest.xml', 'format':'KERNEL'},
        #  {'manifest_url':'http://.../initrd.manifest.xml','format':'RAMDISK'}
        #  {'manifest_url':'http://.../centos.manifest.xml','format':'PARTITION'}
        self.image_manifests = image_manifests
    def __repr__(self):
        return 'instance-store conversion task:%s' % self.task_id

    def __str__(self):
        manifest_str = ''
        for manifest in self.image_manifests:
            manifest_str = manifest_str + '\n' + str(manifest)
        return 'instance-store conversion task - id: %s, bucket: %s, prefix: %s, manifests: %s' % (self.task_id, self.bucket, self.prefix, manifest_str)

    def process_task(self):
        return True

class VolumeImagingTask(ImagingTask):
    def __init__(self, task_id, manifest_url=None, volume_id=None):
        ImagingTask.__init__(self, task_id, "import_volume")
        self.manifest_url = manifest_url
        self.volume_id = volume_id
        self.ec2_conn = EucaEC2Connection(host_name=config.get_clc_host(),
                          aws_access_key_id=config.get_access_key_id(),
                          aws_secret_access_key=config.get_secret_access_key(),
                          security_token = config.get_security_token(),
                          port=config.get_clc_port(),
                          path=config.get_ec2_path())

    def __repr__(self):
        return 'volume conversion task:%s' % self.task_id

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

    def attach_volume(self):
        if self.volume_id == None:
            raise RuntimeError('This import does not have a volume')
        devices_before = self.get_block_devices()
        device_name = self.next_device_name(devices_before)
        instance_id = config.get_worker_id()
        worker.log.debug('attaching volume {0} to {1} as {2}'.format(self.volume_id, instance_id, device_name))
        if not self.ec2_conn.attach_volume_and_wait(self.volume_id, instance_id, device_name):
            raise RuntimeError('Can not attach volume {0} to the instance {1}'.format(
                              self.volume_id, instance_id)) #todo: add specific error?
        new_block_devices = self.get_block_devices()
        new_device_name = new_block_devices[0] # can it be different from device_name?
        return new_device_name

    def download_data(self, manifest_url, device_name):
        manifest = manifest_url.replace('imaging@', '')
        try:
            return subprocess.Popen(['/usr/libexec/eucalyptus/euca-run-workflow', 'down-parts/write-raw', '--url-image', manifest, '--output-path', device_name], stderr=subprocess.PIPE)
        except Exception, err:
            worker.log.error('Could not start data download: %s' % err)
            return None

    def detach_volume(self):
        if self.volume_id == None:
            raise RuntimeError('This import does not have volume id')
        worker.log.debug('detaching volume {0}'.format(self.volume_id))
        devices_before = self.get_block_devices()
        if not self.ec2_conn.detach_volume_and_wait(self.volume_id):
            raise RuntimeError('Can not dettach volume {0}'.format(self.volume_id)) #todo: add specific error?
        if len(devices_before)==len(self.get_block_devices()):
            raise RuntimeError('Volume was not dettached in {0} seconds'.format(timeout_sec)) #todo: add specific error?
        return True

    def run_download_to_volume(self, device_to_use):
        # download image to the block device and monitor process
        process = self.download_data(self.manifest_url, device_to_use)
        if process != None:
            while process.poll() == None:
                # get bytes transfered
                output=process.stderr.readline().strip()
                bytes_transfered = 0
                try:
                    res = json.loads(output)
                    bytes_transfered = res['status']['bytes_downloaded']
                except Exception:
                    worker.log.warn("Downloadimage subprocess reports invalid status")
                worker.log.debug("Status %s, %d" % (output, bytes_transfered))
                if self.report_running(self.volume_id, bytes_transfered): 
                    worker.log.info('Conversion task %s was canceled by server' % self.task_id)
                    process.kill()
                else:
                    time.sleep(10)

    def process_task(self):
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
                    self.report_failed(self.volume_id, 0)
                    self.detach_volume()
                    return False
                try:
                    self.run_download_to_volume(device_to_use)
                    done_with_errors = False
                except Exception, err:
                     worker.log.error('Failed to download data: %s' % err)
            else:
                worker.log.info('There is no volume id. Importing to Object Storage')
                raise RuntimeError('Import to Object Storage is not supported')
            # detaching volume
            if device_to_use != None:
                worker.log.info('Detaching volume %s' % self.volume_id)
                self.detach_volume()
            # set DONE or FAILED state
            if done_with_errors:
                self.report_failed(self.volume_id)
                return False
            else:
                self.report_done(self.volume_id, image_size)
                return True
        except Exception, err:
            worker.log.error('Failed to process task: %s' % err)
