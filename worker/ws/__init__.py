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
import boto.utils
from boto.resultset import ResultSet
from boto.ec2.regioninfo import RegionInfo
from boto.ec2.connection import EC2Connection
from boto.iam.connection import IAMConnection
from worker.ssl.server_cert import ServerCertificate
from worker.ws.instance_import_task import InstanceImportTask
import time
import M2Crypto
from collections import Iterable
from lxml import objectify
import worker
import worker.config as config


def connect_euare(host_name=None, port=80, path="services/Euare", aws_access_key_id=None,
                  aws_secret_access_key=None, security_token=None, **kwargs):
    return EucaEuareConnection(host_name=host_name, port=port, path=path, aws_access_key_id=aws_access_key_id,
                               aws_secret_access_key=aws_secret_access_key, security_token=security_token,
                               **kwargs)


def connect_imaging_worker(host_name=None, port=80, path="services/Imaging", aws_access_key_id=None,
                           aws_secret_access_key=None, security_token=None, **kwargs):
    return EucaISConnection(host_name=host_name, port=port, path=path, aws_access_key_id=aws_access_key_id,
                            aws_secret_access_key=aws_secret_access_key, security_token=security_token,
                            **kwargs)


def connect_ec2(host_name=None, port=80, path="services/Eucalyptus", aws_access_key_id=None,
                aws_secret_access_key=None, security_token=None, **kwargs):
    return EucaEC2Connection(host_name=host_name, port=port, path=path, aws_access_key_id=aws_access_key_id,
                             aws_secret_access_key=aws_secret_access_key, security_token=security_token,
                             **kwargs)


class EucaEC2Connection(object):
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 host_name=None, is_secure=False, path='services/Eucalyptus',
                 security_token=None, validate_certs=False, port=80):
        region = RegionInfo(name='eucalyptus', endpoint=host_name)
        self.conn = EC2Connection(region=region, host=host_name, aws_access_key_id=aws_access_key_id,
                                  aws_secret_access_key=aws_secret_access_key, port=port,
                                  path=path, security_token=security_token, is_secure=is_secure,
                                  validate_certs=validate_certs)
        self.conn.APIVersion = '2013-08-15'  #TODO: set new version?
        self.conn.http_connection_kwargs['timeout'] = 30

    def attach_volume(self, volume_id, instance_id, device_name):
        return self.conn.attach_volume(volume_id, instance_id, device_name)

    def detach_volume(self, volume_id):
        return self.conn.detach_volume(volume_id)

    def describe_volumes(self, volume_ids=None):
        return self.conn.get_all_volumes(volume_ids)

    def describe_volume(self, volume_id=None):
        if volume_id == None:
            raise RuntimeError("There is no volume_id provoded")
        res = self.describe_volumes([volume_id, 'verbose'])
        if len(res) != 1:
            raise RuntimeError("Can't describe volume %s" % volume_id)
        else:
            vol = res[0]
            if vol.status == 'in-use':
                return {'status': vol.attachment_state(), 'instance_id': vol.attach_data.instance_id}
            else:
                return {'status': vol.status}

    def detach_volume_and_wait(self, volume_id, timeout_sec=3000, task_id=None):
        '''
        Attempts to detach a volume, and wait for the volume's status
        to become 'available'. Will raise RunTimeError upon failure.
        :param volume_id: string representing volume id. ie: vol-abcd1234
        :param timeout_sec: Timeout to wait for volume to detach in seconds
        '''
        vol = None
        vols = self.conn.get_all_volumes(volume_id)
        for vol in vols:
            if vol.id == volume_id:
                break
        if not vol or vol.id != volume_id:
            raise RuntimeError('Failed to lookup volume:"{0}" from system'
                               .format(volume_id))
        attachment_state = vol.attachment_state()
        if attachment_state and attachment_state != 'detaching':
            vol.detach()
        start = time.time()
        elapsed = 0
        while elapsed < timeout_sec:
            vol.update()
            if vol.status == 'available' or vol.status.startswith('delet'):
                worker.log.debug('detach_volume_and_wait volume status: "%s"' % vol.status, process=task_id)
                return
            time.sleep(5)
            elapsed = time.time() - start
        # Volume has failed to detach within the given timeout raise error
        instance = 'unknown'
        if hasattr(vol, "attach_data"):
            instance = str(vol.attach_data.instance_id)
        raise RuntimeError('Volume:"{0}" failed to detach from:"{1}". '
                           'Status:"{2}", elapsed: {3}/{4}'
                           .format(vol.id, instance, vol.status, elapsed, timeout_sec))

    def attach_volume_and_wait(self,
                               volume_id,
                               instance_id,
                               device_name,
                               poll_interval=5,
                               timeout_sec=300):
        '''
        Attempts to attach a volume and wait for the correct attached status.

        '''
        vol = None
        vols = self.conn.get_all_volumes(volume_id)
        for vol in vols:
            if vol.id == volume_id:
                break
        if not vol or vol.id != volume_id:
            raise RuntimeError('Failed to lookup volume:"{0}" from system'
                               .format(volume_id))
        # Attempt to attach
        vol.attach(instance_id=instance_id, device=device_name)
        # Monitor attached state to attached or failure
        start = time.time()
        vol.update()
        while vol.attachment_state() != 'attached':
            time.sleep(poll_interval)
            elapsed = time.time() - start
            # Catch failure states and raise error
            if elapsed > timeout_sec or \
                vol.status == 'available' or \
                vol.status.startswith('delet'):
                raise RuntimeError('Failed to attach volume:"{0}" '
                                   'to attach to:"{1}". Status:"{2}". '
                                   'Elapsed:"{3}/{4}"'.format(volume_id,
                                                          instance_id,
                                                          vol.status,
                                                          elapsed,
                                                          timeout_sec))
            time.sleep(poll_interval)
            vol.update()
        # Final check for correct volume attachment
        attached_id = vol.attach_data.instance_id
        if attached_id != instance_id:
            raise RuntimeError('Volume:"{0}" not attached to correct '
                               'instance:"{1}". Status:"{2}". Attached:"{3}".'
                               'Elapsed:"{4}/{5}"'.format(volume_id,
                                                          instance_id,
                                                          vol.status,
                                                          attached_id,
                                                          elapsed,
                                                          timeout_sec))


class EucaISConnection(object):
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 host_name=None, is_secure=False, path='services/Imaging',
                 security_token=None, validate_certs=False, port=80):
        region = RegionInfo(name='eucalyptus', endpoint=host_name)
        self.conn = EC2Connection(region=region, host=host_name, aws_access_key_id=aws_access_key_id,
                                  aws_secret_access_key=aws_secret_access_key, port=port,
                                  path=path, security_token=security_token, is_secure=is_secure,
                                  validate_certs=validate_certs)
        self.conn.APIVersion = '2014-02-14'  #TODO: set new version?
        self.conn.http_connection_kwargs['timeout'] = 30

    def get_import_task(self):
        params = {'InstanceId': config.get_worker_id()}
        task = self.conn.get_object('GetInstanceImportTask', params, InstanceImportTask, verb='POST')
        if not task or not task.task_id:
            return None
        else:
            return task

    """
    Communicates conversion status to the server
    Returns True if task should be canceled
    """

    def put_import_task_status(self, task_id=None, status=None, volume_id=None, bytes_converted=None):
        if task_id == None or status == None:
            raise RuntimeError("Invalid parameters")
        params = {'InstanceId': config.get_worker_id(), 'ImportTaskId': task_id, 'Status': status}
        if bytes_converted != None:
            params['BytesConverted'] = bytes_converted
        if volume_id != None:
            params['VolumeId'] = volume_id
        resp = self.conn.make_request('PutInstanceImportTaskStatus', params, path='/', verb='POST')
        if resp.status != 200:
            raise httplib.HTTPException(resp.status, resp.reason, resp.read())
        root = objectify.XML(resp.read())
        return 'true' == root.cancelled.text if hasattr(root, 'cancelled') else False


class EucaEuareConnection(IAMConnection):
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 is_secure=False, port=None, proxy=None, proxy_port=None,
                 proxy_user=None, proxy_pass=None, host_name=None, debug=0,
                 https_connection_factory=None, path='/', security_token=None, validate_certs=True):
        """
        Euca-specific extension to boto's IAM connection. 
        """
        IAMConnection.__init__(self, aws_access_key_id,
                               aws_secret_access_key,
                               is_secure, port, proxy,
                               proxy_port, proxy_user, proxy_pass,
                               host_name, debug, https_connection_factory,
                               path, security_token,
                               validate_certs=validate_certs)

    def download_cloud_certificate(self):
        resp = self.get_response('DownloadCloudCertificate', {})
        result = resp['euca:_download_cloud_certificate_response_type']['euca:download_cloud_certificate_result']
        if not result:
            raise Exception('No certificate is found in the response')
        cert_b64 = result['euca:cloud_certificate']
        if not cert_b64:
            raise Exception('No certificate is found in the response')
        return cert_b64.decode('base64')

    def download_server_certificate(self, cert, pk, euare_cert, auth_signature, cert_arn):
        """
        Download server certificate identified with 'cert_arn'. del_certificate and auth_signature
        represent that the client is authorized to download the certificate

        :type cert_arn: string
        :param cert_arn: The ARN of the server ceritifcate to download
 
        :type delegation_certificate: string
        :param delegation_certificate: The certificate to show that this client is delegated to download the user's server certificate

        :type auth_signature: string
        :param auth_signature: The signature by Euare as a proof that the bearer of delegation_certificate is authorized to download server certificate
 
        """
        timestamp = boto.utils.get_ts()
        msg = cert_arn + "&" + timestamp
        rsa = M2Crypto.RSA.load_key_string(pk)
        msg_digest = M2Crypto.EVP.MessageDigest('sha256')
        msg_digest.update(msg)
        sig = rsa.sign(msg_digest.digest(), 'sha256')
        sig = sig.encode('base64')
        cert = cert.encode('base64')

        params = {'CertificateArn': cert_arn,
                  'DelegationCertificate': cert,
                  'AuthSignature': auth_signature,
                  'Timestamp': timestamp,
                  'Signature': sig}
        resp = self.get_response('DownloadServerCertificate', params)
        result = resp['euca:_download_server_certificate_response_type']['euca:download_server_certificate_result']
        if not result:
            return None
        sig = result['euca:signature']
        arn = result['euca:certificate_arn']
        server_cert = result['euca:server_certificate']
        server_pk = result['euca:server_pk']

        if arn != cert_arn:
            raise Exception("certificate ARN in the response is not valid")
        sig_payload = str(server_cert) + '&' + str(server_pk)
        sig = str(sig)
        # verify the signature to ensure the response came from EUARE
        cert = M2Crypto.X509.load_cert_string(euare_cert)
        verify_rsa = cert.get_pubkey().get_rsa()
        msg_digest = M2Crypto.EVP.MessageDigest('sha256')
        msg_digest.update(sig_payload)
        if verify_rsa.verify(msg_digest.digest(), sig.decode('base64'), 'sha256') != 1:
            raise Exception("invalid signature from EUARE")

        # prep symmetric keys
        parts = server_pk.split("\n")
        if (len(parts) != 2):
            raise Exception("invalid format of server private key")
        symm_key = parts[0]
        cipher = parts[1]
        try:
            raw_symm_key = rsa.private_decrypt(symm_key.decode('base64'), M2Crypto.RSA.pkcs1_padding)
        except Exception, err:
            raise Exception("failed to decrypt symmetric key: " + str(err))
        try:
            cipher = cipher.decode('base64')
            # prep iv and cipher text
            iv = cipher[0:16]
            cipher_text = cipher[16:]

            # decrypt the pk
            cipher = M2Crypto.EVP.Cipher("aes_256_cbc", raw_symm_key, iv, op=0, padding=0)
            txt = cipher.update(cipher_text)
            txt = txt + cipher.final()
            s_cert = ServerCertificate(server_cert.decode('base64'), txt.decode('base64'))
        except Exception, err:
            raise Exception("failed to decrypt the private key: " + str(err))

        return s_cert

