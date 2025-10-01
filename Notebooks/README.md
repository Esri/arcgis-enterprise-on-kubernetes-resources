# Notebook services in ArcGIS Enterprise on Kubernetes
After you've enabled Notebook services in ArcGIS Enterprise on Kubernetes and members in your organization start launching notebooks, a new deployment is created for each member. When a member runs both Standard and Advanced runtimes, this can result in two deployments per member running within the cluster. In the Kubernetes implementation, both runtimes are bundled in a single image to control the capabilities that are enabled at start-up of the pod. This results in a relatively large image size (~27.3GB uncompressed) for each notebook deployment, and because those notebooks can be scheduled on any available node in the cluster, this could lead to a long image pull time for the first-time runs of notebook on nodes where the images are not cached.

For this purpose, a preload daemonset is available to load the notebooks images on each node within the cluster. To preload on a small number of nodes, the use of a selector field is included in the daemonset YAML.

To avoid overlap with the ArcGIS Enterprise on Kubernetes namespace, the cluster administrator must create a separate namespace for the daemonset with the appropriate dockerconfigjson secret as follows:

1. Create namespace:
<br>    a. `kubectl create namespace arcgis-notebook-images`
2. Create image pull secret (optional, not required if using organization registry with IAM or managed identity-based authentication):
<br>    a. `kubectl get secret <siteName>-container-registry -n <organizationNamespace> -o yaml | grep -v '^\s*namespace:\s' | kubectl apply -n arcgis-notebook-images -f -`
<br>        i. The default siteName is `arcgis` and organizationNamespace should be replaced with the namespace where ArcGIS Enterprise on Kubernetes is already deployed.
5. Create daemonset:
<br>    a. Download [YAML file](https://github.com/Esri/arcgis-enterprise-on-kubernetes-resources/blob/main/Notebooks/notebook-image-preloader.yaml)
<br>    b. Edit any necessary fields (i.e. uncomment node selector or change namespace)
<br>    c. Apply YAML file
<br>        i. `kubectl apply -f notebook-image-preloader.yaml`

Note: When applying updates or upgrades to the ArcGIS Enterprise organization, the image tags in the daemonset containers should be updated to match the organization build.
