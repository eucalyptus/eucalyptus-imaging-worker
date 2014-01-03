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

from xml.dom import minidom
from boto.resultset import ResultSet
from boto.ec2.regioninfo import RegionInfo
from boto.ec2.connection import EC2Connection

def connect_clc(host_name=None, aws_access_key_id=None, aws_secret_access_key=None, port=8773, 
                path="internal/Imaging", security_token=None, is_secure=True, validate_certs=True):
    region=RegionInfo(name='eucalyptus', endpoint=host_name)
    return EC2Connection(region=region, port=port, path=path, aws_access_key_id=aws_access_key_id,
                         aws_secret_access_key=aws_secret_access_key, security_token=security_token,
                         is_secure=is_secure, validate_certs=validate_certs)

class ImagingTask():
    def __init__(self, task_id):
        self.task_id = task_id
    
class EucaISConnection():
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 host_name=None, is_secure=False, port=None, path='internal/Imaging',
                 security_token=None, validate_certs=True):
        self.conn = connect_clc(host_name, aws_access_key_id, aws_secret_access_key, port, 
                               path, security_token, is_secure, validate_certs)
        self.conn.http_connection_kwargs['timeout'] = 30

    def get_import_task(self):
        resp=self.conn.make_request('GetInstanceImportTask', {}, path='/', verb='POST')
        if resp.status != 200:
           raise httplib.HTTPException(resp.status, resp.reason, resp.read())
        body=resp.read()
        xmldoc = minidom.parseString(body)
        importTaskElem = xmldoc.getElementsByTagName('euca:importTaskId')
        task_id = None
        
        if len(importTaskElem)>0 and importTaskElem[0].firstChild:
            task_id = importTaskElem[0].firstChild.data      
        if (task_id != None):
            return ImagingTask(task_id)
        else:
            return None

    def put_import_task_status(self, task_id=None, status=None, bytes_converted=None):
        if task_id==None or status==None:
            raise RuntimeError("Invalid parameters")
        params = {'ImportTaskId':taskId, 'Status': status}
        if bytes_converted != None:
            params['BytesConverted'] = bytes_converted
        self.conn.make_request('GetInstanceImportTask', params, path='/', verb='POST')
