import worker
import worker.config as config


def attach_volume(instance_id=None, volume_id=None, device_name='/dev/vdc'):
    if not volume_id or not instance_id:
        print 'volume and instance id must be specified'

    try:
        access_key_id = config.get_access_key_id()
        secret_access_key = config.get_secret_access_key()
        security_token = config.get_security_token()
        con = worker.ws.connect_ec2(aws_access_key_id=access_key_id,
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
        con = worker.ws.connect_ec2(aws_access_key_id=access_key_id,
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
        con = worker.ws.connect_ec2(aws_access_key_id=access_key_id,
                                    aws_secret_access_key=secret_access_key, security_token=security_token)
        volumes = con.describe_volumes([volume_id, 'verbose'])
        print 'describe-volumes: %s' % volumes
    except Exception, err:
        print 'failed to describe volumes: %s' % err
        return 
