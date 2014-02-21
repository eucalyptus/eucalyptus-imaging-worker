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
import os
import httplib2
import service
import boto
import boto.provider

DEFAULT_PID_ROOT = "/var/run/eucalyptus-imaging-service"
DEFAULT_PIDFILE = os.path.join(DEFAULT_PID_ROOT, "eucalyptus-imaging-service.pid")
CONF_ROOT = "/etc/eucalyptus-imaging-service"
RUN_ROOT = "/var/lib/eucalyptus-imaging-service"
SUDO_BIN = "/usr/bin/sudo"

FLOPPY_MOUNT_DIR = "/mnt/floppy"

# Apply default values in case user does not specify
pidfile = DEFAULT_PIDFILE
pidroot = DEFAULT_PID_ROOT
boto_config = None
cred_provider = None
user_data_store={}
QUERY_PERIOD_SEC = 30
def get_provider():
    global boto_config
    global cred_provider
    if not cred_provider:
        if boto_config:
            boto.provider.config = boto.Config(boto_config)
        cred_provider = boto.provider.get_default()
    return cred_provider

def set_boto_config(filename):
    if not os.path.isfile(filename):
        raise Exception('could not find boto config {0}'.format(filename))
    global boto_config
    boto_config = filename

# Update pidfile and pidroot variables in global scope.
# This is called if the user has chosen to use a custom
# pidfile location from the command line.
def set_pidfile(filename):
    global pidfile
    global pidroot
    pidfile = filename
    pidroot = os.path.dirname(pidfile)

def query_user_data():
    resp, content = httplib2.Http().request("http://169.254.169.254/latest/user-data")
    if resp['status'] != '200' or len(content) <= 0:
        raise Exception('could not query the userdata')
    #format of userdata = "key1=value1;key2=value2;..."
    kvlist = content.split(';')
    for word in kvlist:
        kv = word.split('=')
        if len(kv) == 2:
            user_data_store[kv[0]]=kv[1] 

def get_value(key):
    if key in user_data_store:
       return user_data_store[key]
    else:
        query_user_data()
        if key not in user_data_store:
            raise Exception('could not find %s' % key) 
        return user_data_store[key]

def get_access_key_id(): 
    akey = get_provider().get_access_key()
    return akey

def get_secret_access_key():
    skey = get_provider().get_secret_key()
    return skey

def get_security_token():
    token = get_provider().get_security_token()
    return token

def get_clc_host():
    return '169.254.169.254'

def get_clc_port():
    val=get_value('eucalyptus_port')
    if val is not None:
        return int(val)
    else:
        return val

def get_ec2_path():
    return get_value('ec2_path')

def get_imaging_path():
    return get_value('imaging_path')

__availability_zone = None
def get_availability_zone():
    global __availability_zone
    if __availability_zone is None:
        resp, content = httplib2.Http().request("http://169.254.169.254/latest/meta-data/placement/availability-zone")
        if resp['status'] != '200' or len(content) <= 0:
            raise Exception('could not query the metadata for availability zone (%s,%s)' % (resp, content))
        __availability_zone = content
    return __availability_zone

__service_id = None
def get_service_id():
    global __service_id 
    if __service_id is None:
        resp, content = httplib2.Http().request("http://169.254.169.254/latest/meta-data/instance-id")
        if resp['status'] != '200' or len(content) <= 0:
            raise Exception('could not query the metadata for instance id (%s,%s)' % (resp, content))
        __service_id = content
    return __service_id
