# (c) Copyright 2016 Hewlett Packard Enterprise Development Company LP
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

import subprocess
import re
import shlex
import os
from eucaimgworker.logutil import CustomLog
from eucaimgworker import LOGGER_NAME

logger = CustomLog(LOGGER_NAME)


def get_block_devices():
    ret_list = []
    for filename in os.listdir('/dev'):
        if any(filename.startswith(prefix) for prefix in ('sd', 'xvd', 'vd', 'xd')):
            filename = re.sub('\d', '', filename)
            if not '/dev/' + filename in ret_list:
                ret_list.append('/dev/' + filename)
    return ret_list


def run_as_sudo(cmd):
    return run('sudo %s' % cmd)


def run_as_sudo_with_grep(cmd, grep):
    return run_with_grep('sudo %s' % cmd, grep)


def run(cmd):
    p = subprocess.Popen(shlex.split(cmd), stderr=subprocess.PIPE)
    output = p.communicate()
    if p.returncode != 0:
        logger.debug(output)
    return p.returncode


def run_with_grep(cmd, grep):
    proc1 = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE)
    proc2 = subprocess.Popen(shlex.split('grep %s' % grep), stdin=proc1.stdout, stderr=subprocess.PIPE)
    proc1.stdout.close()
    output = proc2.communicate()
    if proc2.returncode != 0:
        logger.debug(output)
    return proc2.returncode
