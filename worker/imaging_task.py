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
import tempfile
import time
import json
import os
import re
import requests
import config
import worker
import subprocess
import traceback
import httplib2
import base64
import threading
from lxml import objectify
import worker.ssl

class TaskThread(threading.Thread):
    def __init__(self, function):
        threading.Thread.__init__(self)
        self.function = function
        self.result = None

    def run(self):
        self.result = self.function()

    def get_result(self):
        return self.result

class ImagingTask(object):
    FAILED_STATE = 'FAILED'
    DONE_STATE = 'DONE'
    EXTANT_STATE = 'EXTANT'

    def __init__(self, task_id, task_type):
        self.task_id = task_id
        self.task_type = task_type
        self.is_conn = worker.ws.connect_imaging_worker(host_name=config.get_clc_host(),
                                                        aws_access_key_id=config.get_access_key_id(),
                                                        aws_secret_access_key=config.get_secret_access_key(),
                                                        security_token=config.get_security_token())
        self.should_run = True
        self.bytes_transferred = None
        self.volume_id = None

    def get_task_id(self):
        return self.task_id

    def get_task_type(self):
        return self.task_type

    def run_task(self):
        raise NotImplementedError()

    def cancel_cleanup(self):
        raise NotImplementedError()

    def process_task(self):
        self.task_thread = TaskThread(self.run_task)
        self.task_thread.start()
        while self.task_thread.is_alive():
            time.sleep(10)
            if not self.report_running(): # cancelled by imaging service
                worker.log.debug('task is cancelled by imaging service', self.task_id)
                self.cancel()
        if not self.is_cancelled():
            if self.task_thread.get_result():
                self.report_done()
                return True
            else:
                self.report_failed()
                return False 
        else:
            return False
  
    def cancel(self):
        #set should_run=False (to stop the task thread)
        self.should_run = False
        if self.task_thread:
            self.task_thread.join() # wait for the task thread to release
        try:
            self.cancel_cleanup() # any task specific cleanup
        except Exception, err:
            worker.log.warn('Failed to cleanup task after cancellation: %s' % err, self.task_id)     

    def is_cancelled(self):
        return not self.should_run

    def report_running(self):
        return self.is_conn.put_import_task_status(self.task_id, ImagingTask.EXTANT_STATE, self.volume_id, self.bytes_transferred)

    def report_done(self):
        self.is_conn.put_import_task_status(self.task_id, ImagingTask.DONE_STATE, self.volume_id, self.bytes_transferred)

    def report_failed(self):
        self.is_conn.put_import_task_status(self.task_id, ImagingTask.FAILED_STATE, self.volume_id, self.bytes_transferred)

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
            ec2_cert = import_task.volume_task.ec2_cert.decode('base64')
            ec2_cert_path = '%s/cloud-cert.pem' % config.RUN_ROOT
            worker.ssl.write_certificate(ec2_cert_path, ec2_cert)
        elif import_task.task_type == "convert_image" and import_task.instance_store_task:
            task = import_task.instance_store_task
            account_id = task.account_id
            access_key = task.access_key
            upload_policy = task.upload_policy
            upload_policy_signature = task.upload_policy_signature
            s3_url = task.s3_url
            ec2_cert = task.ec2_cert.decode('base64')
            ec2_cert_path = '%s/cloud-cert.pem' % config.RUN_ROOT
            worker.ssl.write_certificate(ec2_cert_path, ec2_cert)
            import_images = task.import_images
            converted_image = task.converted_image
            bucket = converted_image.bucket
            prefix = converted_image.prefix
            architecture = converted_image.architecture
            service_key_path = '%s/node-pk.pem' % config.RUN_ROOT
            service_cert_path = '%s/node-cert.pem' % config.RUN_ROOT
            cert_arn = str(task.service_cert_arn)
            cert = worker.ssl.download_server_certificate(cert_arn, task_id=import_task.task_id)
            worker.ssl.write_certificate(service_key_path, cert.get_private_key())
            worker.ssl.write_certificate(service_cert_path, cert.get_certificate())
            task = InstanceStoreImagingTask(import_task.task_id, bucket=bucket, prefix=prefix,
                                            architecture=architecture, owner_account_id=account_id,
                                            owner_access_key=access_key, s3_upload_policy=upload_policy,
                                            s3_upload_policy_signature=upload_policy_signature, s3_url=s3_url,
                                            ec2_cert_path=ec2_cert_path, service_key_path=service_key_path,
                                            import_images=import_images)
        return task

class InstanceStoreImagingTask(ImagingTask):
    def __init__(self, task_id, bucket=None, prefix=None, architecture=None, owner_account_id=None,
                 owner_access_key=None, s3_upload_policy=None, s3_upload_policy_signature=None, s3_url=None,
                 ec2_cert_path=None, service_key_path=None, import_images=[]):
        ImagingTask.__init__(self, task_id, "convert_image")
        self.bucket = bucket
        self.prefix = prefix
        self.architecture = architecture
        self.owner_account_id = owner_account_id
        self.owner_access_key = owner_access_key
        self.s3_upload_policy = base64.b64decode(s3_upload_policy)
        self.s3_upload_policy_signature = s3_upload_policy_signature
        self.s3_url = s3_url
        self.ec2_cert_path = ec2_cert_path
        self.cloud_cert_path = '%s/cloud-cert.pem' % config.RUN_ROOT
        self.service_key_path = service_key_path

        # list of image manifests that will be the sources of conversion
        # see worker/ws/instance_import_task::ImportImage
        # [{'id':'eki-xxxx', 'download_manifest_url':'http://..../vmlinuz.manifest.xml', 'format':'KERNEL'},
        #  {'id':'eri-xxxx', 'download_manifest_url':'http://.../initrd.manifest.xml','format':'RAMDISK'}
        #  {'id':'emi-xxxx', 'download_manifest_url':'http://.../centos.manifest.xml','format':'PARTITION'}
        self.import_images = import_images
        self.process = None

    def __repr__(self):
        return 'instance-store conversion task:%s' % self.task_id

    def __str__(self):
        manifest_str = ''
        for manifest in self.import_images:
            manifest_str = manifest_str + '\n' + str(manifest)
        return 'instance-store conversion task - id: %s, bucket: %s, prefix: %s, manifests: %s' % (
            self.task_id, self.bucket, self.prefix, manifest_str)

    def get_image(self, val):
        for image in self.import_images:
            if image.format == val:
                return image

    @staticmethod
    def get_tmp_file(string):
        temp = tempfile.NamedTemporaryFile()
        temp.write(string)
        temp.flush()
        return temp

    @staticmethod
    def get_manifest_url(url_string):
        if "imaging@" not in url_string:
            raise Exception('invalid manifest URL')
        return url_string

    def run_task(self):
        try:
            params = ['/usr/libexec/eucalyptus/euca-run-workflow',
                      'down-bundle-fs/up-bundle',
                      "--image-manifest-url=%s" % self.get_manifest_url(
                          self.get_image('PARTITION').download_manifest_url),
                      "--kernel-manifest-url=%s" % self.get_manifest_url(
                          self.get_image('KERNEL').download_manifest_url),
                      "--ramdisk-manifest-url=%s" % self.get_manifest_url(
                          self.get_image('RAMDISK').download_manifest_url),
                      '--emi=' + self.get_image('PARTITION').id,
                      '--eki=' + self.get_image('KERNEL').id,
                      '--eri=' + self.get_image('RAMDISK').id,
                      '--decryption-key-path=' + self.service_key_path,
                      '--encryption-cert-path=' + self.ec2_cert_path,
                      '--signing-key-path=' + self.service_key_path,
                      '--prefix=' + self.prefix,
                      '--bucket=' + self.bucket,
                      '--work-dir=/mnt/imaging',
                      '--arch=' + self.architecture,
                      '--account=' + self.owner_account_id,
                      '--access-key=' + self.owner_access_key,
                      '--object-store-url=' + self.s3_url,
                      '--upload-policy=' + self.s3_upload_policy,
                      '--upload-policy-signature=' + self.s3_upload_policy_signature,
                      '--cloud-cert-path=' + self.cloud_cert_path]
            worker.log.debug('Running %s' % ' '.join(params), self.task_id)
            # added for debug TODO: remove later
            self.out_file = open("/tmp/stdout.txt", "wb")
            self.err_file = open("/tmp/stderr.txt", "wb")
            self.process = subprocess.Popen(params, stderr=self.err_file, stdout=self.out_file)
            if not self.process:
                raise Exception('Failed to start the workflow process')
            while not self.is_cancelled() and self.process.poll() == None:
                time.sleep(1)
            if self.process.poll() != None:
                self.out_file.close()
                self.err_file.close()
            if self.process.returncode != None and self.process.returncode == 0:
                return True
            elif self.process.returncode != None:
                worker.log.warn('euca-run-workflow returned code: %d' % self.process.returncode, self.task_id)
                return False
            else:
                worker.log.warn('euca-run-workflow has been killed', self.task_id)
                return False
        except Exception, err:
            worker.log.error('Failed to process task: %s' % err, self.task_id)
            return False

    def cancel_cleanup(self):
        try:
            if self.out_file:
                self.out_file.close()
            if self.err_file:
                self.err_file.close()
            if self.process and self.process.poll()==None:
                self.process.kill()
        except Exception, err:
            worker.log.error('Failed to cleanup during task cancellation: %s' % err, self.task_id)

class VolumeImagingTask(ImagingTask):
    _GIG_ = 1073741824

    def __init__(self, task_id, manifest_url=None, volume_id=None):
        ImagingTask.__init__(self, task_id, "import_volume")
        self.manifest_url = manifest_url
        self.ec2_conn = worker.ws.connect_ec2(
            host_name=config.get_clc_host(),
            aws_access_key_id=config.get_access_key_id(),
            aws_secret_access_key=config.get_secret_access_key(),
            security_token=config.get_security_token())
        self.volume = None
        self.volume_id = volume_id
        if self.volume_id:
            self.volume = self.ec2_conn.conn.get_all_volumes([self.volume_id])
        if not self.volume:
            raise ValueError('Request for volume:"{0}" returned:"{1}"'
                             .format(volume_id, str(self.volume)))
        self.volume = self.volume[0]
        self.volume_attached_dev = None
        self.instance_id = config.get_worker_id()
        self.process = None


    def __repr__(self):
        return 'volume conversion task:%s' % self.task_id

    def __str__(self):
        return ('Task: {0}, manifest url: {1}, volume id: {2}'
                .format(self.task_id, self.manifest_url, self.volume.id))

    def get_partition_size(self, partition):
        p = subprocess.Popen(["sudo", "blockdev", "--getsize64", partition], stdout=subprocess.PIPE)
        t = p.communicate()[0]
        worker.log.debug('The blockdev reported %s for %s' % (t.rstrip('\n'), partition), self.task_id)
        return int(t.rstrip('\n'))

    def add_write_permission(self, partition):
        subprocess.call(["sudo", "chmod", "a+w", partition])

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
        device = re.sub('\d', '', device.strip())
        last_char = device[-1]
        device_prefix = device.rstrip(last_char)
        # todo use boto here instead of metadata? Need sec token then?
        # block_device_mapping = self.ec2_conn.conn.get_instance_attribute(
        #   instance_id=self.instance_id, attribute='blockdevicemapping')

        block_device_mapping = self._get_block_device_mapping_metadata()
        # iterate through local devices as well as cloud block device mapping
        for x in xrange(ord(last_char) + 1, ord('z')):
            next_device = device_prefix + chr(x)
            if (not next_device in all_dev) and \
                    (not next_device in block_device_mapping) and \
                    (not os.path.basename(next_device) in block_device_mapping):
                # Device is not in use locally or in block dev map
                return next_device
        # if a free device was found increment device name and re-enter
        return self.next_device_name(device_prefix + "aa")

    def _get_metadata(self, path, basepath='http://169.254.169.254/'):
        for x in xrange(0, 3):
            try:
                r = requests.get(os.path.join(basepath, path.lstrip('/')))
                r.raise_for_status()
                break
            except:
                if x >= 2:
                    raise
                time.sleep(1)
        return r.content

    def _get_block_device_mapping_metadata(self):
        devlist = []
        bdm_path = '/latest/meta-data/block-device-mapping'
        bdm = self._get_metadata(path=bdm_path)
        for bmap in bdm.splitlines():
            new_dev = self._get_metadata(path=os.path.join(bdm_path, bmap))
            if new_dev:
                devlist.append(new_dev.strip())
        return devlist


    def attach_volume(self, local_dev_timeout=120):
        new_device_name = None
        if not self.volume:
            raise RuntimeError('This import does not have a volume')
        instance_id = self.instance_id
        devices_before = worker.get_block_devices()
        device_name = self.next_device_name(devices_before)
        worker.log.debug('Attaching volume {0} to {1} as {2}'.
                         format(self.volume.id, instance_id, device_name), self.task_id)
        self.ec2_conn.attach_volume_and_wait(self.volume.id,
                                             instance_id,
                                             device_name)
        elapsed = 0
        start = time.time()
        while elapsed < local_dev_timeout and not new_device_name:
            new_block_devices = worker.get_block_devices()
            worker.log.debug('Waiting for local dev for volume: "{0}", '
                             'elapsed:{1}'.format(self.volume.id, elapsed), self.task_id)
            diff_list = list(set(new_block_devices) - set(devices_before))
            if diff_list:
                for dev in diff_list:
                    # If this is virtio attempt to verify vol to dev mapping
                    # using serial number field info
                    if not os.path.basename(dev).startswith('vd'):
                        self.verify_virtio_volume_block_device(
                            volume_id=self.volume.id,
                            blockdev=dev)
                    new_device_name = dev
                    break
            elapsed = time.time() - start
            if elapsed < local_dev_timeout:
                time.sleep(2)
        if not new_device_name:
            raise RuntimeError('Could find local device for volume:"{0}"'
                               .format(self.volume.id))
        self.volume_attached_dev = new_device_name
        return new_device_name

    def verify_virtio_volume_block_device(self,
                                          volume_id,
                                          blockdev,
                                          syspath='/sys/block/'):
        '''
        Attempts to verify a given volume id to a local block device when
        using kvm. In eucalyptus the serial number provides the volume
        id and the requested block device mapping in the
        format: vol-<id>-<dev name>.
        Example: "vol-abcd1234-dev-vdf"
        :param volume_id: string volume id. example. vol-abcd1234
        :param blockdev: block device. Example 'vdf' or '/dev/vdf'
        :param syspath: option dir to begin looking for dev serial num to map
        '''
        if not blockdev.startswith('vd'):
            return
        for devdir in os.listdir(syspath):
            serialpath = os.path.join(syspath + devdir + '/serial')
            if os.path.isfile(serialpath):
                with open(serialpath) as devfile:
                    serial = devfile.read()
                if serial.startswith(volume_id):
                    break
        if os.path.basename(blockdev) == devdir:
            worker.log.debug('Validated volume:"{0}" at dev:"{1}" '
                             'via serial number: '
                             .format(volume_id, blockdev), self.task_id)
            return
        else:
            raise ValueError('Device for volume: {0} could not be verfied'
                             ' against dev:{1}'.format(volume_id, blockdev))

    def download_data(self, manifest_url, device_name):
        manifest = manifest_url.replace('imaging@', '')
        cloud_cert_path = '%s/cloud-cert.pem' % config.RUN_ROOT
        try:
            params = ['/usr/libexec/eucalyptus/euca-run-workflow',
                      'down-parts/write-raw',
                      '--import-manifest-url', manifest,
                      '--output-path', device_name,
                      '--cloud-cert-path', cloud_cert_path]
            worker.log.debug('Running %s' % ' '.join(params), self.task_id)
            return subprocess.Popen(params, stderr=subprocess.PIPE)
        except Exception, err:
            worker.log.error('Could not start data download: %s' % err, self.task_id)
            return None

    def detach_volume(self, timeout_sec=3000, local_dev_timeout=30):
        worker.log.debug('Detaching volume %s' % self.volume.id, self.task_id)
        if self.volume is None:
            raise RuntimeError('This import does not have volume id')
        devices_before = worker.get_block_devices()
        self.volume.update()
        # Do not attempt to detach a volume which is not attached/attaching, or
        # is not attached to this instance
        this_instance_id = config.get_worker_id()
        attached_state = self.volume.attachment_state()
        if not attached_state \
                or not attached_state.startswith('attach') \
                or (hasattr(self.volume, 'attach_data')
                    and self.volume.attach_data.instance_id != this_instance_id):
            self.volume_attached_dev = None
            return True
        # Begin detaching from this instance
        if not self.ec2_conn.detach_volume_and_wait(self.volume.id, timeout_sec=timeout_sec, task_id=self.task_id):
            raise RuntimeError('Can not detach volume {0}'
                               .format(self.volume.id))  #todo: add specific error?
        # If the attached dev is known, verify it is no longer present.
        if self.volume_attached_dev:
            elapsed = 0
            start = time.time()
            devices_after = devices_before
            while elapsed < local_dev_timeout:
                new_block_devices = worker.get_block_devices()
                devices_after = list(set(devices_before) - set(new_block_devices))
                if not self.volume_attached_dev in devices_after:
                    break
                else:
                    time.sleep(2)
                elapsed = time.time() - start
            if self.volume_attached_dev in devices_after:
                # todo: add specific error?
                self.volume.update()
                worker.log.error('Volume:"{0}" state:"{1}". Local device:"{2}"'
                                 'found on guest after {3} seconds'
                                 .format(self.volume.id,
                                         self.volume.status,
                                         self.volume.local_blockdev,
                                         timeout_sec), self.task_id)
        return True

    def run_task(self):
        try:
            device_to_use = None
            manifest = self.get_manifest()
            image_size = int(manifest.image.size)
            if self.volume is not None:
                if long(int(self.volume.size) * self._GIG_) < image_size:
                    raise ValueError('Volume:"{1}" size:"{1}" is too small '
                                     'for image to be processed:"{2}"'
                                     .format(self.volume.id,
                                             self.volume.size,
                                             image_size))
                worker.log.info('Attaching volume %s' % self.volume.id, self.task_id)
                device_to_use = self.attach_volume()
                if self.is_cancelled():
                    raise Exception('Task is cancelled')
                worker.log.debug('Using %s as destination' % device_to_use, self.task_id)
                device_size = self.get_partition_size(device_to_use)
                worker.log.debug('Attached device size is %d bytes' % device_size, self.task_id)
                worker.log.debug('Needed for image/volume %d bytes' % image_size, self.task_id)
                if image_size > device_size:
                    raise Exception('Device is too small for the image/volume')
                try:
                    self.add_write_permission(device_to_use)
                    self.process = self.download_data(self.manifest_url, device_to_use)
                    if self.process is not None:
                        self.wait_with_status(self.process)
                    else:
                        raise Exception('Cannot start workflow process')
                    if self.process.returncode == None:
                        raise Exception('Process was killed')
                    elif self.process.returncode != 0:
                        raise Exception('Return code from the process: %d' % self.process.returncode)
                except Exception, err:
                    raise Exception('Failed to download to volume: %s' % err)
            else:
                raise Exception('No volume id is found for import-volume task')
            return True
        except Exception, err:
            tb = traceback.format_exc()
            worker.log.error(str(tb) + '\nFailed to process task: %s' % err, self.task_id)
            return False
        finally:
            # detaching volume
            if device_to_use is not None and self.volume_id:
                worker.log.info('Detaching volume %s' % self.volume_id, self.task_id)
                self.ec2_conn.detach_volume_and_wait(volume_id=self.volume_id, task_id=self.task_id)

    def wait_with_status(self, process):
        while not self.is_cancelled() and process.poll() is None:
            # get bytes transferred
            output = process.stderr.readline().strip()
            try:
                res = json.loads(output)
                self.bytes_transferred = res['status']['bytes_downloaded']
            except Exception, ex:
                worker.log.warn("Download image subprocess reports invalid status. Error: %s" % output, self.task_id)
            if self.bytes_transferred:
                worker.log.debug("Status %s, bytes transferred: %d" % (output, self.bytes_transferred), self.task_id)
            time.sleep(2)

    def cancel_cleanup(self):
        try:
            if self.process and self.process.poll()==None:
                self.process.kill()
        except Exception, err:
            worker.log.error('Failed to cleanup during task cancellation: %s' % err, self.task_id)

