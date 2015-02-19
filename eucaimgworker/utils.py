# Copyright 2009-2015 Eucalyptus Systems, Inc.
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
import os
import subprocess
import sys
import re


def get_block_devices():
    ret_list = []
    for filename in os.listdir('/dev'):
        if any(filename.startswith(prefix) for prefix in ('sd', 'xvd', 'vd', 'xd')):
            filename = re.sub('\d', '', filename)
            if not '/dev/' + filename in ret_list:
                ret_list.append('/dev/' + filename)
    return ret_list


def run_as_sudo(cmd):
    return subprocess.call('sudo %s' % cmd, shell=True)
