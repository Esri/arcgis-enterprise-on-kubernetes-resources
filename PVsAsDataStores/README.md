Starting at ArcGIS Enterprise on Kubernetes version 11.4, you can register a folder data store that uses a persistent volumne (PV). See [Manage folder data stores](https://enterprise-k8s.arcgis.com/en/latest/administer/system-managed-data-stores.htm#ESRI_SECTION1_6A836545AC0645B48C8B11631714A935) for more information about these PV-based folder data stores. Four example YAMLs are provided:

- [local-pv-sc.yaml](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/PVsAsDataStores/local-pv-sc.yaml): A storage class for a local PV
- [local-pv.yaml](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/PVsAsDataStores/local-pv.yaml): A local PV used for routing or geocoding
- [nfs-pv.yaml](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/PVsAsDataStores/nfs-pv.yaml): An NFS share accessed as a PV
- [windows-pv.yaml](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/PVsAsDataStores/windows-pv.yaml): A Windows (SMB) share accessed as a PV

When registering a PV-based folder data store, you must also provide a volume specification. The volume specification is a collection of properties that are used to create the persistent volume claim (PVC) object. The elements included in the volume specification are used for matching and binding the created PVC to the child PV object. At version 11.5, you can provide the volume specification values in Enterprise Manager when creating the data store. In version 11.4 however, you must provide a JSON file that contains the volume specification. 

## Volume specification JSON (11.4 only)

 Use of volumeName and labels is recommended to ensure a single PV is identified as a candidate for matching.

| Property | Description | Required |
|--|--|--|
| storageClassName | Must match the storage class defined in the PV. If a default storage class is enabled within the cluster, the created PVC will have the default storage class name automatically appended, so a storage class should be added to the PV and specified in this field. |  |
| resources | This value must match or be smaller than the storage size defined in the PV. | X |
| accessModes | ReadWriteOnce, ReadWriteMany, ReadOnlyMany. This logical field does not restrict scheduling of pods across multiple nodes so if specific nodes should be used (as in the case for local PV) those nodes should be identified in the PV spec itself. | X |
| volumeMode | Must be Filesystem. | X |
| volumeName | Should match the name of the PV, not required but helps to identify a unique PV that matches the PVC. |  |
| labels | Operates as a label selector during binding, since many PVs can have identical labels use of volumeName in addition is the preferred method for unique PV identification. |  |

___

Example JSON file contents that match the PV defined by [local-pv.yaml](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/PVsAsDataStores/local-pv.yaml):
```json
{
    "accessModes": ["ReadWriteOnce"],
    "volumeMode": "Filesystem",
    "resources": {
        "requests": {
            "storage": "100Gi"
        }
    },
    "storageClassName": "my-local-storage", 
    "volumeName": "arcgis-enterprise-folder-pv-2"
}
```
___

Example JSON file contents that match the PV defined by [nfs-pv.yaml](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/PVsAsDataStores/nfs-pv.yaml):
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
___

Example JSON file contents that match the PV defined by [windows-pv.yaml](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/PVsAsDataStores/windows-pv.yaml):
```json
{
    "accessModes":["ReadOnlyMany"],
    "volumeMode": "Filesystem",
    "resources": {
        "requests":{
          "storage": "100Gi"
        }
    },
    "storageClassName": "",
    "volumeName": "arcgis-enterprise-windows-smb-pv"
}
```
