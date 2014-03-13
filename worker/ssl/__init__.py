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

import worker.ws
import worker.config as config
import os
global __cloud_certificate_file
def get_cloud_certificate_file():
    __cloud_certificate_file = None
    if __cloud_certificate_file is None:
        con = worker.ws.connect_euare(host_name=config.get_clc_host(), aws_secret_access_key=config.get_secret_access_key(), 
                                      security_token=config.get_security_token())
        val = con.download_cloud_certificate()
        if val == None:
            raise Exception('could not get cloud certificate')
        f = open(config.CLOUD_CERT_FILE, 'w')
        f.write(val)
        f.close()
        os.chmod(config.CLOUD_CERT_FILE, 0400)
        __cloud_certificate_file = config.CLOUD_CERT_FILE
    return __cloud_certificate_file

