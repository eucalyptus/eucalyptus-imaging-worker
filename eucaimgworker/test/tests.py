import eucaimgworker
import eucaimgworker.config as config
from eucaimgworker.floppy import FloppyCredential


def download_server_cert(cert_arn=None):
    if not cert_arn:
        cert_arn = "arn:aws:iam::965529822009:server-certificate/ImagingCert-imgworker"
    try:
        f = FloppyCredential()
        access_key_id = config.get_access_key_id()
        secret_access_key = config.get_secret_access_key()
        security_token = config.get_security_token()
        con = eucaimgworker.ws.connect_euare(aws_access_key_id=access_key_id,
                                      aws_secret_access_key=secret_access_key, security_token=security_token)
        cert = con.download_server_certificate(f.get_instance_pub_key(), f.get_instance_pk(), f.get_iam_pub_key(),
                                               f.get_iam_token(), cert_arn)
        print '%s\n%s' % (cert.get_certificate(), cert.get_private_key())

        return cert;
    except Exception, err:
        print 'failed to download the server certificate: %s' % err
        return


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
