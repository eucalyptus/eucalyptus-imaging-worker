from boto.resultset import ResultSet

def match_name(name, param):
    if name==param or 'euca:%s'%name == param:
        return True
    return False

class InstanceImportTask(object):
    def __init__(self, parent=None):
        self.task_id = None
        self.task_type = None
        self.volume_task = None
        self.instance_store_task = None

    def __repr__(self):
        return 'InstanceImportTask:%s' % self.task_id
 
    def startElement(self, name, attrs, connection): 
        if match_name('instanceStoreTask', name):
            self.instance_store_task = InstanceStoreTask()
            return self.instance_store_task
        elif match_name('volumeTask', name):
            self.volume_task = VolumeTask()
            return self.volume_task
        else:
            return None
        
    def endElement(self, name, value, connection):
        if match_name('importTaskId', name):
            self.task_id = value
        elif match_name('importTaskType',name):
            self.task_type = value
        else:
            setattr(self, name, value)

class InstanceStoreTask(object):
    def __init__(self, parent=None):
        self.bucket = None
        self.prefix = None
        self.image_manifests = []

    def startElement(self, name, attrs, connection): 
        if match_name('imageManifestSet',name):
            self.image_manifests =  ResultSet([('item', ImageManifest)])
            return self.image_manifests
        else:
            return None

    def endElement(self, name, value, connection):
        if match_name('bucket',name):
            self.bucket = value
        elif match_name('prefix',name):
            self.prefix = value
        else:
            setattr(self, name, value)

class VolumeTask(object):
    def __init__(self, parent=None):
        self.volume_id = None
        self.image_manifests = []

    def startElement(self, name, attrs, connection): 
        if match_name('imageManifestSet', name):
            self.image_manifests =  ResultSet([('item', ImageManifest)])
            return self.image_manifests
        else:
            return None

    def endElement(self, name, value, connection):
        if match_name('volumeId', name):
            self.volume_id = value
        else:
            setattr(self, name, value)

class ImageManifest(object):
    def __init__(self, parent=None):
        self.manifest_url = None
        self.format = None

    def startElement(self, name, attrs, connection): 
        pass

    def endElement(self, name, value, connection):
        if match_name('manifestUrl', name):
            self.manifest_url = value
        elif match_name('format', name):
            self.format = value
        else:
            setattr(self, name, value)

    def __str__(self):
        return 'manifest-url:%s, format:%s' % (self.manifest_url, self.format)
