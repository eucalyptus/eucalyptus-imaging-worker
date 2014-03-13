from boto.resultset import ResultSet

class InstanceImportTask(object):
    def __init__(self, parent=None):
        self.task_id = None
        self.task_type = None
        self.volume_task = None
        self.instance_store_task = None

    def __repr__(self):
        return 'InstanceImportTask:%s' % self.task_id
 
    def startElement(self, name, attrs, connection): 
        if name == 'instanceStoreTask':
            self.instance_store_task = InstanceStoreTask()
            return self.instance_store_task
        elif name == 'volumeTask':
            self.volume_task = VolumeTask()
            return self.volume_task
        else:
            return None
        
    def endElement(self, name, value, connection):
        if name == 'importTaskId':
            self.task_id = value
        elif name == 'importTaskType':
            self.task_type = value
        else:
            setattr(self, name, value)

class InstanceStoreTask(object):
    def __init__(self, parent=None):
        self.bucket = None
        self.prefix = None
        self.image_manifests = []

    def startElement(self, name, attrs, connection): 
        if name == 'imageManifestSet':
            self.image_manifests =  ResultSet([('item', ImageManifest)])
            return self.image_manifests
        else:
            return None

    def endElement(self, name, value, connection):
        if name == 'bucket':
            self.bucket = value
        elif name == 'prefix':
            self.prefix = value
        else:
            setattr(self, name, value)

class VolumeTask(object):
    def __init__(self, parent=None):
        self.volume_id = None
        self.image_manifests = []

    def startElement(self, name, attrs, connection): 
        if name == 'imageManifestSet':
            self.image_manifests =  ResultSet([('item', ImageManifest)])
            return self.image_manifests
        else:
            return None

    def endElement(self, name, value, connection):
        if name == 'volumeId':
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
        if name == 'manifestUrl':
            self.manifest_url = value
        elif name == 'format':
            self.format = value
        else:
            setattr(self, name, value)

    def __str__(self):
        return 'manifest-url:%s, format:%s' % (self.manifest_url, self.format)
