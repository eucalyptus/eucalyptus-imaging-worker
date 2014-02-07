import service
import service.config as config
from service.floppy import FloppyCredential

def download_server_cert(cert_arn=None):
    if not cert_arn:
        cert_arn = "arn:aws:iam::965529822009:server-certificate/ImagingCert-imgservice"
    try:
        f = FloppyCredential() 
        host = config.get_clc_host()
        access_key_id = config.get_access_key_id()
        secret_access_key = config.get_secret_access_key()
        security_token = config.get_security_token()
        con = service.ws.connect_euare(host_name=host, aws_access_key_id = access_key_id, aws_secret_access_key=secret_access_key, security_token=security_token)
        cert= con.download_server_certificate(f.get_instance_pub_key(), f.get_instance_pk(), f.get_iam_pub_key(), f.get_iam_token(), cert_arn)
        print '%s\n%s' % (cert.get_certificate(), cert.get_private_key())

        return cert;
    except Exception, err:
        print 'failed to download the server certificate: %s' % err
        return
