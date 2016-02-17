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

import eucaimgworker
import eucaimgworker.config as config


def attach_volume(instance_id=None, volume_id=None, device_name='/dev/vdc'):
    if not volume_id or not instance_id:
        print 'volume and instance id must be specified'

    try:
        access_key_id = config.get_access_key_id()
        secret_access_key = config.get_secret_access_key()
        security_token = config.get_security_token()
        con = eucaimgworker.ws.connect_ec2(aws_access_key_id=access_key_id,
                                    aws_secret_access_key=secret_access_key, security_token=security_token)
        con.attach_volume(volume_id, instance_id, device_name)
        print 'volume %s attached to instance %s at %s' % (volume_id, instance_id, device_name)
    except Exception, err:
        print 'failed to attach volume: %s' % err
        return


def detach_volume(volume_id=None):
    if not volume_id:
        print 'volume id must be specified'

    try:
        access_key_id = config.get_access_key_id()
        secret_access_key = config.get_secret_access_key()
        security_token = config.get_security_token()
        con = eucaimgworker.ws.connect_ec2(aws_access_key_id=access_key_id,
                                    aws_secret_access_key=secret_access_key, security_token=security_token)
        con.detach_volume(volume_id)
        print 'volume %s detached' % volume_id
    except Exception, err:
        print 'failed to detach volume: %s' % err
        return


def describe_volume(volume_id=None):
    if not volume_id:
        print 'volume id must be specified'
    try:
        access_key_id = config.get_access_key_id()
        secret_access_key = config.get_secret_access_key()
        security_token = config.get_security_token()
        con = eucaimgworker.ws.connect_ec2(aws_access_key_id=access_key_id,
                                    aws_secret_access_key=secret_access_key, security_token=security_token)
        volumes = con.describe_volumes([volume_id, 'verbose'])
        print 'describe-volumes: %s' % volumes
    except Exception, err:
        print 'failed to describe volumes: %s' % err
        return