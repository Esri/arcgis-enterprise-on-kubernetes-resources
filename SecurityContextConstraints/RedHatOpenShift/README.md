# Security Context Constraints

These YAML resources offer two configuration options:
1. If the cluster nodes have been modified to increase the VM_MAX_MAP_COUNT to 212644 then 1-restricted-v2-esri.yaml can be applied to the cluster by the cluster admin and all ArcGIS Enterprise on Kubernetes pods will be admitted.

2. If the cluster administrator is unable to modify the underlying node image to include the VM_MAX_MAP_COUNT increase, then the arcgis-enterprise-elastic service account must be allowed to run as privileged, while the rest of the service accounts can run in the restricted SCC. The cluster administrator should apply both 2a-restricted-v2-esri.yaml and 2b-privileged-esri.yaml and only the spatiotemporal pod(s) will be allowed to run in the privileged mode while all other workloads will run in the restricted mode.
