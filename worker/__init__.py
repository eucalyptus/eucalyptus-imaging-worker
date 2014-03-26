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
import subprocess

__version__ = '1.0.0-dev'
Version = __version__

def start_worker():
    if subprocess.call('sudo modprobe floppy > /dev/null', shell=True) != 0:
        log.error('failed to load floppy driver')
    # The worker is shipped in CentOS hvm image so checking /dev/vdb
    # veirfy that we are in a VM first so we don't format someone's /dev/vdb
    try:
        worker.config.get_worker_id()
        if subprocess.call('ls -la /dev/vdb > /dev/null', shell=True) != 0 or subprocess.call('ls -la /mnt > /dev/null', shell=True) != 0:
            log.error('failed to find /dev/vdb or /mnt')
        else:
            if subprocess.call('sudo mount | grep /mnt > /dev/null', shell=True) == 1:
                if subprocess.call('sudo mkfs.ext3 /dev/vdb > /dev/null', shell=True) != 0 or subprocess.call('sudo mount /dev/vdb /mnt > /dev/null', shell=True) != 0:
                    log.error('failed to format and mount /dev/vdb')
                else:
                    log.info('/dev/vdb was successfully formatted and mounted to /mnt')
            else:
                log.info('/dev/vdb is alredy mounted to /mnt')
    except:
        log.error("Can't detect VM's id")
        sys.exit(1)
    # download cloud certificate and save it
    try:
        con = worker.ws.connect_euare(host_name=config.get_clc_host(), aws_access_key_id=config.get_access_key_id(),
                                      aws_secret_access_key=config.get_secret_access_key(), security_token=config.get_security_token())
        cert = con.download_cloud_certificate()
        f = open('%s/cloud.pem'%config.RUN_ROOT, 'w')
        f.write(cert)
        f.close()
    except:
        log.error("Can't get cloud certificate")
        sys.exit(1)
    WorkerLoop().start()
