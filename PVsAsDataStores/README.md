When registering a persistent volume as a folder data store, a JSON file must be constructed that contains the volume specification. The volume specification is a collection of properties that are used to create the persistent volume claim (PVC) object. The elements included in the volume specification are used for matching and binding of the created PVC to the child PV object. Use of volumeName and labels is recommended to ensure a single PV is identified as a candidate for matching.

| Property | Description | Required |
|--|--|--|
| storageClassName | Must match the storage class defined in the PV. If a default storage class is enabled within the cluster, the created PVC will have the default storage class name automatically appended, so a storage class should be added to the PV and specified in this field. |  |
| resources | This value must match or be smaller than the storage size defined in the PV. | X |
| accessModes | ReadWriteOnce or ReadWrite many, this logical field does not restrict scheduling of pods across multiple nodes so if specific nodes should be used (as in the case for local PV) those nodes should be identified in the PV spec itself. | X |
| volumeMode | Must be Filesystem. | X |
| volumeName | Should match the name of the PV, not required but helps to identify a unique PV that matches the PVC. |  |
| labels | Operates as a label selector during binding, since many PVs can have identical labels use of volumeName in addition is the preferred method for unique PV identification. |  |

___

Example JSON file contents for an NFS PV:
```json
{
    "storageClassName": "arcgis-folder-pv",
    "resources": {
      "requests": {
        "storage": "100Gi"
      }
    },
    "accessModes": ["ReadWriteMany"],
    "volumeMode": "Filesystem",
    "volumeName": "arcgis-enterprise-folder-pv-1",
    "labels": {
      "serviceType": "byReferenceMap",
      "shareType": "NFS"
    }
}
```

This would match a PV defined by the following YAML:
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: arcgis-enterprise-folder-pv-1
  labels:
    serviceType: byReferenceMap
    shareType: NFS
spec:
  capacity:
    storage: 100Gi
  accessModes:
    - ReadWriteMany
  nfs:
    server: example-nfs-server.domain.com
    path: /share/path/to/service/data
  storageClassName: arcgis-folder-pv
```

___

Example JSON file contents for a local PV:
```json
{
    "accessModes": ["ReadWriteOnce"],
    "volumeMode": "Filesystem",
    "resources": {
        "requests": {
            "storage": "100Gi"
        }
    },
    "storageClassName": "arcgis-folder-pv", 
    "volumeName": "arcgis-enterprise-folder-pv-2"
}
```

This would match a PV defined by the following YAML:
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: arcgis-enterprise-folder-pv-2
spec:
  capacity:
    storage: 100Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: arcgis-folder-pv
  local:
    path: /path/to/service/data
  nodeAffinity: # The node affinity part is optional if you have the data on all the nodes in your cluster
    required:
      nodeSelectorTerms:
      - matchExpressions:
        - key: serviceType
          operator: In
          values:
          - byReferenceMap
```
