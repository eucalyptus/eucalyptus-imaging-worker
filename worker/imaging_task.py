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
import glob
import shutil
import fcntl
import re
import requests
import config
import worker
import subprocess
import traceback
import httplib2
import threading
import tempfile
from defusedxml.ElementTree import fromstring
import worker.ssl
from task_exit_codes import *
from worker.failure_with_code import FailureWithCode
from worker.floppy import FloppyCredential


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
    RAW_FORMAT = 'RAW'
    VMDK_FORMAT = 'VMDK'

    EXTANT_STATUS_REPORT_INTERVAL = 30

    def __init__(self, task_id, task_type):
        self.task_id = task_id
        self.task_type = task_type
        self.is_conn = worker.ws.connect_imaging_worker(aws_access_key_id=config.get_access_key_id(),
                                                        aws_secret_access_key=config.get_secret_access_key(),
                                                        security_token=config.get_security_token())
        self.should_run = True
        self.bytes_transferred = None
        self.volume_id = None
        self.task_thread = None

    def get_task_id(self):
        return self.task_id

    def get_task_type(self):
        return self.task_type

    def get_input_format(self):
        return self.input_format

    def run_task(self):
        raise NotImplementedError()

    def cancel_cleanup(self):
        raise NotImplementedError()

    def prepare(self):
        try:
            for f in glob.iglob('/mnt/imaging/*'):
                os.remove(f) if os.path.isfile(f) else shutil.rmtree(f)
        except Exception, err:
            worker.log.error("Can't clean up /mnt/imaging/ due to {0}".format(str(err)))

    def process_task(self):
        self.prepare()
        self.task_thread = TaskThread(self.run_task)
        self.task_thread.start()
        while self.task_thread.is_alive():
            time.sleep(self.EXTANT_STATUS_REPORT_INTERVAL)
            if not self.report_running():  # cancelled by imaging service
                worker.log.debug('task is cancelled by imaging service', self.task_id)
                self.cancel()
        if not self.is_cancelled():
            run_result = self.task_thread.get_result()
            if run_result['code'] == TASK_DONE:
                self.report_done()
                return True
            else:
                self.report_failed(run_result)
                return False
        else:
            return True

    def cancel(self):
        #set should_run=False (to stop the task thread)
        self.should_run = False
        if self.task_thread:
            self.task_thread.join()  # wait for the task thread to release
        try:
            self.cancel_cleanup()  # any task specific cleanup
        except Exception, err:
            worker.log.warn('Failed to cleanup task after cancellation: %s' % err, self.task_id)

    def is_cancelled(self):
        return not self.should_run

    def report_running(self):
        return self.is_conn.put_import_task_status(self.task_id, ImagingTask.EXTANT_STATE, self.volume_id,
                                                   self.bytes_transferred)

    def report_done(self):
        self.is_conn.put_import_task_status(self.task_id, ImagingTask.DONE_STATE, self.volume_id,
                                            self.bytes_transferred)

    def report_failed(self, run_result):
        self.is_conn.put_import_task_status(self.task_id, ImagingTask.FAILED_STATE, self.volume_id,
                                            self.bytes_transferred, run_result['code'],
                                            run_result['message'] if 'message' in run_result else None)

    """
    param: instance_import_task (object representing ImagingService's message)
    return: ImagingTask
    """

    @staticmethod
    def from_import_task(import_task):
        if not import_task:
            return None
        task = None
        f = FloppyCredential(task_id=import_task.task_id)
        ec2_cert_path = '%s/cloud-cert.pem' % config.RUN_ROOT
        worker.ssl.write_certificate(ec2_cert_path, f.get_cloud_cert())
        if import_task.task_type == "import_volume" and import_task.volume_task:
            volume_id = import_task.volume_task.volume_id
            manifests = import_task.volume_task.image_manifests
            manifest_url = None
            image_format = None
            if manifests and len(manifests) > 0:
                manifest_url = manifests[0].manifest_url
                image_format = manifests[0].format
            task = VolumeImagingTask(import_task.task_id, manifest_url, volume_id, image_format)
        return task


class VolumeImagingTask(ImagingTask):
    _GIG_ = 1073741824

    def __init__(self, task_id, manifest_url=None, volume_id=None, input_format=ImagingTask.RAW_FORMAT):
        ImagingTask.__init__(self, task_id, "import_volume")
        self.manifest_url = manifest_url
        self.ec2_conn = worker.ws.connect_ec2(
            aws_access_key_id=config.get_access_key_id(),
            aws_secret_access_key=config.get_secret_access_key(),
            security_token=config.get_security_token())
        self.volume = None
        self.volume_id = volume_id
        if self.volume_id:
            self.volume = self.ec2_conn.conn.get_all_volumes([self.volume_id, 'verbose'])
        if not self.volume:
            raise ValueError('Request for volume:"{0}" returned:"{1}"'
                             .format(volume_id, str(self.volume)))
        self.volume = self.volume[0]
        self.volume_attached_dev = None
        self.instance_id = config.get_worker_id()
        self.process = None
        self.input_format = input_format

    def __repr__(self):
        return 'volume conversion task:%s' % self.task_id

    def __str__(self):
        return ('Task: {0}, manifest url: {1}, volume id: {2}, data format: {3}'
                .format(self.task_id, self.manifest_url, self.volume.id, self.input_format))

    def get_partition_size(self, partition):
        p = subprocess.Popen(["sudo", "blockdev", "--getsize64", partition], stdout=subprocess.PIPE)
        t = p.communicate()[0]
        worker.log.debug('The blockdev reported %s for %s' % (t.rstrip('\n'), partition), self.task_id)
        return int(t.rstrip('\n'))

    def add_write_permission(self, partition):
        worker.log.debug('Setting permissions for %s' % partition)
        subprocess.call(["sudo", "chmod", "a+w", partition])


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
            raise FailureWithCode('This import does not have a volume', INPUT_DATA_FAILURE)
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
                        try:
                            self.verify_virtio_volume_block_device(
                                volume_id=self.volume.id,
                                blockdev=dev)
                        except ValueError, ex:
                            raise FailureWithCode(ex, ATTACH_VOLUME_FAILURE)
                    new_device_name = dev
                    break
            elapsed = time.time() - start
            if elapsed < local_dev_timeout:
                time.sleep(2)
        if not new_device_name:
            raise FailureWithCode('Could find local device for volume:"%s"' % self.volume.id, ATTACH_VOLUME_FAILURE)
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

    def get_image_size_from_manifest(self):
        if "imaging@" not in self.manifest_url:
            raise FailureWithCode('Invalid manifest URL', INPUT_DATA_FAILURE)
        resp, content = httplib2.Http().request(self.manifest_url.replace('imaging@', ''))
        if resp['status'] != '200' or len(content) <= 0:
            raise FailureWithCode('Could not download the manifest file', DOWNLOAD_DATA_FAILURE)
        root = fromstring(content)
        if len(root.getiterator('image')) == 1:
            image_el = root.getiterator('image')[0]
        else:
            raise FailureWithCode('Could not process the manifest file', DOWNLOAD_DATA_FAILURE)
        if len(image_el.getiterator('size')) == 1:
            size_el = image_el.getiterator('size')[0]
        else:
            raise FailureWithCode('Could not process the manifest file', DOWNLOAD_DATA_FAILURE)
        return int(size_el.text)

    # errors are catch by caller
    def start_download_process(self, manifest_url, device_name, validate_size=True):
        manifest = manifest_url.replace('imaging@', '')
        cloud_cert_path = '%s/cloud-cert.pem' % config.RUN_ROOT
        params = ['/usr/libexec/eucalyptus/euca-run-workflow',
                  'down-parts/write-raw',
                  '--import-manifest-url', manifest,
                  '--output-path', device_name,
                  '--cloud-cert-path', cloud_cert_path]
        if not validate_size:
            params.append('--skip-size-validation')
        worker.log.debug('Running %s' % ' '.join(params), self.task_id)
        # create process with system default buffer size and make its stderr non-blocking
        self.process = subprocess.Popen(params, stderr=subprocess.PIPE)
        fd = self.process.stderr
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    @staticmethod
    def get_free_space_for_dir(dir_name):
        df = subprocess.Popen(["df", dir_name], stdout=subprocess.PIPE)
        output = df.communicate()[0]
        device, size, used, available, percent, mountpoint = \
            output.split("\n")[1].split()
        return int(available) * 1024;

    def run_task(self):
        device_to_use = None
        try:
            image_size = self.get_image_size_from_manifest()
            if self.volume is not None:
                if long(int(self.volume.size) * self._GIG_) < image_size:
                    raise FailureWithCode('Volume:"{1}" size:"{1}" is too small '
                                          'for image to be processed:"{2}"'
                                          .format(self.volume.id,
                                                  self.volume.size,
                                                  image_size), INPUT_DATA_FAILURE)
                if self.is_cancelled():
                    return {'code': TASK_CANCELED}
                worker.log.info('Attaching volume %s' % self.volume.id, self.task_id)
                device_to_use = self.attach_volume()
                worker.log.debug('Using %s as destination' % device_to_use, self.task_id)
                device_size = self.get_partition_size(device_to_use)
                worker.log.debug('Attached device size is %d bytes' % device_size, self.task_id)
                worker.log.debug('Needed for image/volume %d bytes' % image_size, self.task_id)
                download_file = None
                if image_size > device_size:
                    raise FailureWithCode('Device is too small for the image/volume', INPUT_DATA_FAILURE)
                try:
                    self.add_write_permission(device_to_use)
                    if self.is_cancelled():
                        return {'code': TASK_CANCELED}

                    if self.input_format == ImagingTask.RAW_FORMAT:
                        self.start_download_process(self.manifest_url, device_to_use)
                    elif self.input_format == ImagingTask.VMDK_FORMAT:
                        # In the future a piping processing should be added, for now:
                        # step 1. download file locally
                        # step 2. convert into raw using qemu-img
                        # step 3. move data to attached disk
                        dir_size = VolumeImagingTask.get_free_space_for_dir('/mnt/imaging')
                        #todo: find out if real compressed size can be obtained
                        if dir_size < image_size * 1.2:
                            raise FailureWithCode("There is not enough space at for VMDK image "
                                                  "conversion", INSUFFICIENT_DISK_SIZE)
                        download_file = tempfile.NamedTemporaryFile(dir='/mnt/imaging', delete=False)
                        download_file.close()
                        # download manifest for VMDK import has size for unpacked image, skipp size validation
                        self.start_download_process(self.manifest_url, download_file.name, validate_size=False)
                except Exception, err:
                    worker.log.error('Failure to start workflow process %s' % err)
                    return {'code': err.failure_code, 'message': err.message}
                if self.process is not None:
                    self.wait_with_status(self.process)
                else:
                    worker.log.error('Cannot start workflow process')
                    return {'code': WORKFLOW_FAILURE}
                if self.process.returncode is None:
                    if self.is_cancelled():
                        return {'code': TASK_CANCELED}
                    else:
                        worker.log.error('Process was killed')
                        return {'code': WORKFLOW_FAILURE}
                elif self.process.returncode != 0:
                    worker.log.error('Return code from the workflow process is not 0. Code: %d'
                                     % self.process.returncode)
                    return {'code': WORKFLOW_FAILURE}

                if self.input_format == ImagingTask.VMDK_FORMAT:
                    try:
                        raw_file_name = download_file.name + '.raw'
                        params = ['qemu-img', 'convert', '-O', 'raw', download_file.name, raw_file_name]
                        worker.log.debug('Running %s' % ' '.join(params), self.task_id)
                        df = subprocess.Popen(params, stdout=subprocess.PIPE)
                        output = df.communicate()[0]
                        if df.returncode != 0:
                            worker.log.error('Failed to run VMDK conversion process: %s' % output)
                            return {'code': WORKFLOW_FAILURE}
                        worker.log.debug("Removing tmp VMDK file")
                        os.remove(download_file.name)
                        params = ['dd', 'if=%s' % raw_file_name, 'of=%s' % device_to_use, 'bs=10M']
                        worker.log.debug('Running %s' % ' '.join(params), self.task_id)
                        df = subprocess.Popen(params, stderr=subprocess.PIPE)
                        output = df.communicate()[0]
                        if df.returncode != 0:
                            worker.log.error('Failed to move converted image to attached device %s' % output)
                            return {'code': WORKFLOW_FAILURE}
                        worker.log.debug("Removing tmp RAW file")
                        os.remove(raw_file_name)
                    except Exception, err:
                        worker.log.error('Failure to convert VMDK to RAW or transfer file to volume %s' % err)
                        return {'code': WORKFLOW_FAILURE}

            else:
                worker.log.error('No volume id is found for import-volume task')
                return {'code': INPUT_DATA_FAILURE}

            return {'code': TASK_DONE}

        except Exception, err:
            tb = traceback.format_exc()
            worker.log.error(str(tb) + '\nFailed to process task: %s' % err, self.task_id)
            if type(err) is FailureWithCode:
                return {'code': err.failure_code, 'message': err.message}
            else:
                return {'code': GENERAL_FAILURE}

        finally:
            if device_to_use is not None and self.volume_id:
                worker.log.info('Detaching volume %s' % self.volume_id, self.task_id)
                try:
                    self.ec2_conn.detach_volume_and_wait(volume_id=self.volume_id, task_id=self.task_id)
                except Exception:
                    return {'code': DETACH_VOLUME_FAILURE}

    def wait_with_status(self, process):
        worker.log.debug('Waiting for download process', self.task_id)
        while not self.is_cancelled() and process.poll() is None:
            try:
                # get bytes transferred
                line = process.stderr.readline()
                if line:
                    line = line.strip()
                    try:
                        res = json.loads(line)
                        self.bytes_transferred = res['status']['bytes_downloaded']
                    except Exception, ex:
                        worker.log.warn(
                            "Download image subprocess reports invalid status. Output: %s. Error: %s" % (line, ex),
                            self.task_id)
                    if self.bytes_transferred:
                        worker.log.debug("Status %s, bytes transferred: %d" % (line, self.bytes_transferred),
                                         self.task_id)
            except:
                pass

    # don't catch exceptions since they should be catch by the caller
    def cancel_cleanup(self):
        if self.process and self.process.poll() is None:
            self.process.kill()