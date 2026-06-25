<!--
# Copyright 2026 Esri
#
# Licensed under the Apache License Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
-->

Deploy ArcGIS Enterprise on Kubernetes on AKS Node Auto Provisioning
===
Table of contents
---
  * [Introduction](#introduction)
  * [Prepare the client workstation](#prepare-the-client-workstation)
  * [Create an Azure Kubernetes Service cluster](#create-an-azure-kubernetes-service-cluster)
  * [Install cluster dependencies](#install-cluster-dependencies)
  * [Deploy ArcGIS Enterprise on Kubernetes](#deploy-arcgis-enterprise-on-kubernetes)
  * [Create DNS record](#create-dns-record)
  * [Create your ArcGIS Enterprise on Kubernetes organization](#create-your-arcgis-enterprise-on-kubernetes-organization)
  * [Access your ArcGIS Enterprise on Kubernetes organization](#access-your-arcgis-enterprise-on-kubernetes-organization)
  * [Verify the cluster](#verify-the-cluster)
  * [Teardown](#teardown)

Introduction
---
The following will provide guidance on setting up a client workstation, provisioning an Azure Kubernetes Service (AKS) cluster with Node Auto Provisioning (NAP) enabled, and deploying ArcGIS Enterprise on Kubernetes.

AKS NAP automates compute provisioning using Karpenter-based NodePools, replacing the fixed node groups used in the standard AKS deployment. An Azure Load Balancer handles ingress from the internet to the internal cluster network. Azure Workload Identity is used to grant Azure credentials to ArcGIS pods, since NAP restricts pod access to the node metadata service (IMDS).

The commands provided in this guide may need to be modified to meet your organizational needs. Placeholders, denoted as <variable\>, must be replaced with the relevant deployment information prior to running the command.


Prepare the client workstation
---
### 1. Install kubectl
&emsp;a. Download kubectl
```shell
curl -LO https://dl.k8s.io/release/v1.36.2/bin/linux/amd64/kubectl
```

&emsp;b. Add executable permissions and move to location on path
```shell
chmod +x kubectl && \
sudo mv kubectl /usr/local/bin/
```

&emsp;&emsp;Reference: https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/

### 2. Install and configure Azure CLI
&emsp;a. Install Azure CLI
```shell
curl -L https://aka.ms/InstallAzureCli | bash
```

&emsp;&emsp;Reference: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=script

&emsp;b. Confirm installation and configure Azure CLI
```shell
az version

az init

az login
```

&emsp;&emsp;Reference: https://learn.microsoft.com/en-us/cli/azure/azure-cli-configuration

### 3. Set environment variables
First, list available Kubernetes versions for your target region to identify a supported version:
```shell
az aks get-versions --location <region> --output table
```

Then set all variables:
```shell
export CLUSTER_NAME="<cluster-name>"
export RESOURCE_GROUP="<resource-group-name>"
export LOCATION="<region>"
export K8S_VERSION="<k8s-version>"
export NAMESPACE="<k8s-namespace-for-arcgis>"
export SITE_CONTEXT="<site-context-for-arcgis>"
```

### 4. Download ArcGIS Enterprise on Kubernetes deployment scripts and locate license file
&emsp;a. Sign in to My Esri and download deployment scripts and license file

&emsp;b. Extract deployment scripts
```shell
tar zxf ArcGIS_Enterprise_Kubernetes_*.tar.gz -C <destinationPath>
```


Create an Azure Kubernetes Service cluster
---
AKS NAP requires Azure CNI overlay networking and a dedicated resource group. Creating the cluster without default NodePools gives you full control over workload placement and scaling behavior through Karpenter NodePools.

### 1. Create resource group
```shell
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
```

&emsp;&emsp;Reference: https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-cli

### 2. Create NAP-enabled AKS cluster
Workload Identity and the OIDC issuer are enabled here so that ArcGIS pods can authenticate with Azure services without relying on IMDS. `--node-provisioning-default-pools None` prevents AKS from auto-creating Karpenter NodePool objects, allowing you to define them explicitly in the next section.
```shell
az aks create \
  --name $CLUSTER_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --kubernetes-version $K8S_VERSION \
  --node-provisioning-mode Auto \
  --network-plugin azure \
  --network-plugin-mode overlay \
  --network-dataplane azure \
  --node-provisioning-default-pools None \
  --node-count 2 \
  --enable-managed-identity \
  --enable-oidc-issuer \
  --enable-workload-identity \
  --generate-ssh-keys
```

&emsp;&emsp;Note: AKS always creates one system node pool at cluster creation to run system components (CoreDNS, kube-proxy, etc.). Use `--node-count 2` or higher for production clusters to maintain CoreDNS availability across node failures. Cluster creation typically takes 5-10 minutes.

&emsp;&emsp;Reference: https://learn.microsoft.com/en-us/azure/aks/node-auto-provisioning

### 3. Connect to the cluster
```shell
az aks get-credentials \
  --name $CLUSTER_NAME \
  --resource-group $RESOURCE_GROUP
```

Verify the connection:
```shell
kubectl get nodes
```

### 4. Taint the system node pool
By default, the AKS system node pool has no taints, so user workloads can land on it. Apply the `CriticalAddonsOnly` taint to reserve it exclusively for system components:
```shell
az aks nodepool update \
  --name nodepool1 \
  --cluster-name $CLUSTER_NAME \
  --resource-group $RESOURCE_GROUP \
  --node-taints "CriticalAddonsOnly=true:NoSchedule"
```

&emsp;&emsp;Note: Kubernetes system pods (CoreDNS, kube-proxy, etc.) already carry a toleration for `CriticalAddonsOnly=true:NoSchedule` and will continue to run on the system pool. All other workloads without that toleration will be scheduled exclusively onto NAP-provisioned nodes.

&emsp;&emsp;Reference: https://learn.microsoft.com/en-us/azure/aks/use-node-taints


Install cluster dependencies
---
### 1. Configure node scheduling
AKS NAP uses an AKSNodeClass and NodePools to control how workload nodes are provisioned, replacing fixed managed node groups.

> [!IMPORTANT]
> - Seperate NodePools should be used for stateful data store workloads to ensure proper isolation and scheduling using labels and taints.
> - A dedicated NodePool should be used for GPU-accelerated workloads with appropriate instance type requirements and taints to prevent scheduling non-GPU workloads there.
> - All NodePools must have limits defined to prevent unbounded node provisioning.
> - Disruption budgets should be configured to control how and when nodes can be consolidated or deprovisioned.

&emsp;a. Create the AKSNodeClass referenced by your NodePools
```shell
cat << EOF | kubectl apply -f -
apiVersion: karpenter.azure.com/v1beta1
kind: AKSNodeClass
metadata:
  name: default
spec:
  imageFamily: Ubuntu
  osDiskSizeGB: 300
EOF
```

&emsp;&emsp;Reference: https://learn.microsoft.com/en-us/azure/aks/node-auto-provisioning

&emsp;b. Apply NodePools for each workload type. General-Purpose NodePool for generic ArcGIS workloads:
```shell
cat << EOF | kubectl apply -f -
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: general-purpose
  annotations:
    kubernetes.io/description: "General purpose NodePool for generic workloads"
spec:
  template:
    metadata:
      labels:
        nodeType: general-purpose
    spec:
      nodeClassRef:
        group: karpenter.azure.com
        kind: AKSNodeClass
        name: default
      requirements:                   # Use requirements to control which instance types Karpenter can provision for this NodePool. Adjust values based on workload needs and expected demand patterns.
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: kubernetes.io/os
          operator: In
          values: ["linux"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: karpenter.azure.com/sku-name
          operator: In
          values: ["Standard_D8as_v4"]
  limits:                     # Set limits to prevent overprovisioning - adjust values based on expected workload demand
    cpu: "160"
    memory: "640Gi"
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 15m
    budgets:
    - reasons: ["Drifted"]     # Apply specifically to drifted nodes
      nodes: "0"               # Block all drift-related replacements
    - nodes: "10%"             # Default budget at other times
EOF
```

&emsp;&emsp;Stateful NodePool for Relational Store and other stateful data store components:
```shell
cat << EOF | kubectl apply -f -
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: stateful-nodepool
  annotations:
    kubernetes.io/description: "Dedicated NodePool for stateful data store workloads"
spec:
  template:
    metadata:
      labels:
        nodeType: stateful-purpose
        workload: stateful
    spec:
      nodeClassRef:
        group: karpenter.azure.com
        kind: AKSNodeClass
        name: default
      taints:
        - key: workload
          value: stateful
          effect: NoSchedule
      requirements:               # Use requirements to control which instance types Karpenter can provision for this NodePool. Adjust values based on workload needs and expected demand patterns.
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: kubernetes.io/os
          operator: In
          values: ["linux"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: karpenter.azure.com/sku-name
          operator: In
          values: ["Standard_D8as_v4"]
  limits:                     # Set limits to prevent overprovisioning - adjust values based on expected workload demand
    cpu: "160"
    memory: "640Gi"
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 15m
    budgets:
    - reasons: ["Drifted"]     # Apply specifically to drifted nodes
      nodes: "0"               # Block all drift-related replacements
    - nodes: "10%"             # Default budget at other times
EOF
```

&emsp;&emsp;Note: Ensure data store pods include matching tolerations for the `workload=stateful:NoSchedule` taint.

&emsp;&emsp;GPU NodePool for GPU-accelerated ArcGIS workloads:
```shell
cat << EOF | kubectl apply -f -
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu-nodepool
  annotations:
    kubernetes.io/description: "GPU NodePool for ArcGIS workloads"
spec:
  template:
    metadata:
      labels:
        workload: gpu
    spec:
      nodeClassRef:
        group: karpenter.azure.com
        kind: AKSNodeClass
        name: default
      taints:
        - key: nvidia.com/gpu
          effect: NoSchedule
      requirements:               # Use requirements to control which instance types Karpenter can provision for this NodePool. Adjust values based on workload needs and expected demand patterns.
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: kubernetes.io/os
          operator: In
          values: ["linux"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: karpenter.azure.com/sku-name
          operator: In
          values: ["Standard_NC8as_T4_v3"]
  limits:                     # Set limits to prevent overprovisioning - adjust values based on expected workload demand
    cpu: "40"
    memory: "160Gi"
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 15m
    budgets:
    - reasons: ["Drifted"]     # Apply specifically to drifted nodes
      nodes: "0"               # Block all drift-related replacements
    - nodes: "10%"             # Default budget at other times
EOF
```

&emsp;&emsp;Reference: https://karpenter.sh/docs/concepts/nodepools/


### 2. Create storage class for backup store
The default AKS storage class uses `reclaimPolicy: Delete`, which removes the underlying disk when the PVC is deleted. Create a separate storage class with `reclaimPolicy: Retain` for the ArcGIS backup store to protect against accidental data loss:

```shell
kubectl apply -f sc_reclaim_retain.yaml
```

&emsp;&emsp;Reference: [sc_reclaim_retain.yaml](../../StorageClasses/AzureKubernetesService/sc_reclaim_retain.yaml)


Deploy ArcGIS Enterprise on Kubernetes
---
### 1. Populate deploy.properties file
Follow instructions from [Run the deployment script in silent mode](https://enterprise-k8s.arcgis.com/en/latest/deploy/run-the-deployment-script.htm#ESRI_SECTION1_930D8184D9E9480BB679ABED1743A8CE) in _Run the deployment script_.

Note: ArcGIS Enterprise uses application-level encryption and stores secrets as Kubernetes secrets. It does not have the functionality to integrate with secrets managers such as Azure Key Vault.

Note: `K8S_NAMESPACE` must match the `NAMESPACE` variable and `ARCGIS_SITENAME`/`CONTEXT` must match the `SITE_CONTEXT` variable exported in the "Set environment variables" step.

<details>
<summary>Example deploy.properties file contents:</summary>
<br>

```yaml
# Configuration properties for ArcGIS Enterprise on Kubernetes deployment
#
# ------------------------------------
# DEPLOYMENT PLATFORM
# ------------------------------------
#
# Ingress controller service type
#
# Possible values for INGRESS_TYPE:
#
#   NodePort        - Exposes the Service on each Node's IP at a static port (the NodePort). 
#                     You'll be able to contact the NodePort Service, from outside the cluster, 
#                     by requesting <NodeIP>:<NodePort>.
#   LoadBalancer    - Exposes the Service externally using a cloud provider's load balancer.
#                     The load balancer is created and configured automatically as a part of 
#                     the deployment.
#
INGRESS_TYPE="LoadBalancer"
#
# Possible values for LOAD_BALANCER_TYPE (must choose one if INGRESS_TYPE="LoadBalancer", else 
# leave it blank):
#
#   azure-external   - Azure Load Balancer (External)
#   azure-internal   - Azure Load Balancer (Internal)
#   aws-nlb-external - AWS Network Load Balancer (External)
#   aws-nlb-internal - AWS Network Load Balancer (Internal)
#   gcp-external     - Google Cloud Platform TCP Load Balancer (External)
#   gcp-internal     - Google Cloud Platform TCP Load Balancer (Internal)
#   generic-lb       - Generic load balancer type
#
LOAD_BALANCER_TYPE="azure-external"
#
# Set INGRESS_SERVICE_USE_CLUSTER_IP to true if you plan to use a cluster-level ingress
# controller or OpenShift route for incoming traffic (formerly USE_OPENSHIFT_ROUTE).
INGRESS_SERVICE_USE_CLUSTER_IP=false
#
# Use a pre-configured static public IP address and DNS label with the load balancer
# (optional).
#
LOAD_BALANCER_IP=""
#
# NodePort value in the range 30000-32767 (optional). 
# Leave it blank if you want Kubernetes Control Plane to assign an available port. 
#
NODE_PORT_HTTPS=""

# ------------------------------------
# NAMESPACE
# ------------------------------------
#
# The Kubernetes cluster namespace where ArcGIS Enterprise on Kubernetes will be deployed.
#
K8S_NAMESPACE="arcgis"

# ------------------------------------
# SITENAME
# ------------------------------------
#
# Do not edit the following property
#
ARCGIS_SITENAME="arcgis"

# ------------------------------------
# ENCRYPTION KEYFILE
# ------------------------------------
# The encryption keyfile is a plain text file used for AES-256 encryption/decryption
# of passwords. The contents of this file is arbitrary plain text and SHOULD NOT
# contain any passwords. This file should remain in a fixed location and the contents
# should not change.
ENCRYPTION_KEYFILE="/data/k8s/keyfile.txt"

# ------------------------------------
# CONTAINER REGISTRY
# ------------------------------------
#
# The registry host used to log into the container registry (Docker Hub).
#
REGISTRY_HOST="docker.io"
#
REGISTRY_REPO="esridocker"
#
# Full registry path to pull images.
#
CONTAINER_REGISTRY="${REGISTRY_HOST}/${REGISTRY_REPO}"
#
# Set USE_DOCKER_CONFIG_FILE_AS_REGISTRY_SECRET=true to create the registry secret based on the
# credentials stored in current user's $HOME/.docker/config file instead of those
# defined below.  If the environment variable DOCKER_CONFIG is set then that filename
# will be used instead of $HOME/.docker/config.
#
USE_DOCKER_CONFIG_FILE_AS_REGISTRY_SECRET=false
#
# Set CONTAINER_REGISTRY_AUTHENTICATION_TYPE to one of two accepted values:
#
#     credential - Use usename/password registry authentication
#     integrated - The cluster manages registry authentication
#
# When set to "integrated" the CONTAINER_REGISTRY_USERNAME and the
# CONTAINER_REGISTRY_PASSWORD properties are ignored.
#
CONTAINER_REGISTRY_AUTHENTICATION_TYPE="credential"
#
# Registry username for an account with permissions to pull from the Registry URL specified above.
# This will be used to create a registry secret.
#
CONTAINER_REGISTRY_USERNAME="docker_user"
#
# Registry password for the username specified above.
# This will be used to create a registry secret.
#
# NOTE: This password is AES-256 encrypted using the ENCRYPTION_KEYFILE specified above.
#
# To create an AES-256 encrypted password:
#
#    % echo "my.registry.password" | tools/password-encrypt/password-encrypt.sh -f /path/to/keyfile.txt
#
# That command will output an encrypted string.  Set CONTAINER_REGISTRY_PASSWORD to that encrypted value.
#
CONTAINER_REGISTRY_PASSWORD="U2FsdGVkX19gXwvyDcKh8owl6SjHYEPH7Xz66s8ehRWivyfFox9TnpehuvZiijBm"
#
# Registry secret name for container credentials.
#
CONTAINER_IMAGE_PULL_SECRET_NAME="${ARCGIS_SITENAME}-container-registry"
#	
# The default version tag for pulling images.	
#
VERSION_TAG="${VERSION_TAG:-12.1.0.8325}"

# ------------------------------------
# FULLY QUALIFIED DOMAIN NAME
# ------------------------------------
#
# The fully qualified domain name (FQDN) to access ArcGIS Enterprise on Kubernetes. 
# This FQDN points to a load balancer, reverse proxy, edge router, or other web front-end
# configured to route traffic to the ingress controller.
# For example: <hostname>.<Domain>.com
#
ARCGIS_ENTERPRISE_FQDN="gis.prod.organization.com"
#
# Enter the context path to be used in the URL for ArcGIS Enterprise on Kubernetes. 
# For example, the context path of 'https://<FQDN>/arcgis/admin' would be 'arcgis'. 
# The path needs to be single level; more than one level is not supported.
#
CONTEXT="arcgis"
#
# URL with the specified reverse proxy or load balancer with the site context.
#
ROOT_ORG_BASE_URL="https://${ARCGIS_ENTERPRISE_FQDN}/${CONTEXT}/"

# ------------------------------------
# TLS CERTIFICATE
# ------------------------------------
#
# Choose one of the options below to enable HTTPS communication to the ingress 
# controller using Transport Layer Security (TLS). Unused options in this section 
# should be defined with empty quotes "". 
#
# Option 1: Use an existing Kubernetes TLS secret that contains a private key and a certificate.
# Enter the name of the existing TLS secret:
#
INGRESS_SERVER_TLS_SECRET="prod-wildcard-cert"
#
# Option 2: Use a .pfx file that contains the private key and certificate. Enter the full path 
# and password of the .pfx file:
#
# NOTE: This password is AES-256 encrypted using the ENCRYPTION_KEYFILE specified above
INGRESS_SERVER_TLS_PFX_FILE=""
INGRESS_SERVER_TLS_PFX_PSSWD=""
#
# Option 3: Use PEM format private Key (.key file) and certificate (.crt file). Enter the full
# path of the .key and .crt files:
#
INGRESS_SERVER_TLS_KEY_FILE=""
INGRESS_SERVER_TLS_CRT_FILE=""
#
# Option 4: Generate a self-signed certificate. Enter the common name for the self-signed 
# certificate:
#
INGRESS_SERVER_TLS_SELF_SIGN_CN=""

# ------------------------------------
# ADDITIONAL PROPERTIES
# ------------------------------------
#
# If you cannot run a privileged container, you can set the value to false and you
# will need to manually increase vm.max_map_count to 262144 by running the
# "sysctl -w vm.max_map_count=262144" command as root on each kubernetes node.
ALLOWED_PRIVILEGED_CONTAINERS=true

# Each container has a property called ImagePullPolicy which defines the
# behavior of pulling images from the container registry while starting a
# container. The default value is "IfNotPresent" which means the image is
# pulled only if it is not already present locally.
CONTAINER_IMAGE_PULL_POLICY="Always"

# HTTP Strict Transport Security
INGRESS_HSTS_ENABLED=false

# TLS protocol supported
INGRESS_SSL_PROTOCOLS="TLSv1.2 TLSv1.3"

# Supported Cipher Suites
INGRESS_SSL_CIPHERS="ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES256-SHA:ECDHE-RSA-CHACHA20-POLY1305:AES256-GCM-SHA384:AES256-SHA256:AES256-SHA:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES128-SHA:AES128-GCM-SHA256:AES128-SHA256:AES128-SHA:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA"

# Disabling this property will prevent any network policies from being created when deploying and configuring
# an ArcGIS Enterprise on Kubernetes organization. This decreases the overall security posture of the software
# and should only be done by administrators that have special requirements around network policy objects or
# have implemented separate controls to protect cross-namespace and external network access to pod networks.
ENABLE_NETWORK_POLICIES=true

# If your Kubernetes cluster has a domain name other than cluster.local, use this
# property to specify the domain name
K8S_CLUSTER_DOMAIN="cluster.local"

# If you are deploying ArcGIS Enterprise on Kubernetes and your 
# Kubernetes cluster spans three or more availability zones, update 
# 'kubernetes.io/hostname' to 'topology.kubernetes.io/zone'
K8S_AVAILABILITY_TOPOLOGY_KEY="kubernetes.io/hostname"

# Custom ingress annotations
#
# Allow for additional annotations to be added to the LoadBalancer ingress
# service created during deployment.
#
# Use the following syntax:
#
# INGRESS_CUSTOM_ANNOTATION1="key=value"              # simple values
# INGRESS_CUSTOM_ANNOTATION2='key={"foo": "bar"}'     # for values with quotes
#
# Examples:
#
# INGRESS_CUSTOM_ANNOTATION1="service.beta.kubernetes.io/aws-load-balancer-attributes=deletion_protection.enabled=true,load_balancing.cross_zone.enabled=true"
# INGRESS_CUSTOM_ANNOTATION2='cloud.google.com/app-protocols={"https": "HTTPS"}'
#
# You can append additional annotation properties by incrementing the suffix.
# For example:
#
# INGRESS_CUSTOM_ANNOTATION4=""
#
INGRESS_CUSTOM_ANNOTATION1=""
INGRESS_CUSTOM_ANNOTATION2=""
INGRESS_CUSTOM_ANNOTATION3=""

# ------------------------------------
# CLUSTER-LEVEL INGRESS CONTROLLER YAML FILENAME (Optional)
#
# If you have indicated that you would like to use a cluster-level ingress
# controller (by setting INGRESS_SERVICE_USE_CLUSTER_IP=true) for incoming
# traffic, use one of the YAML templates that can be found in the
# setup/templates/layer-7-templates folder to create or integrate with a
# layer 7 load balancer that routes incoming traffic to your ArcGIS Enterprise
# deployment:
#
#    aws-alb-external.yaml.template
#    aws-alb-internal.yaml.template
#    azure-agw-ingress-controller.yaml.template
#    gcp-alb-external.yaml.template
#    gcp-alb-internal.yaml.template
#    user-defined-ingress.yaml.template
#
# Copy one of these templates locally (remove the .template suffix) and add your
# load balancer configuration info.
#
# Then set CLUSTER_INGRESS_CONTROLLER_YAML_FILENAME to the full path of this
# file. This file can be deleted following a successful deployment. If one of
# these templates does not apply to your deployment pattern, you can also
# supply one of your own custom YAML files.
#
CLUSTER_INGRESS_CONTROLLER_YAML_FILENAME=""

# ------------------------------------
# ADD CUSTOM VARIABLES HERE
# ------------------------------------
#
```
</details>

### 2. Run deploy.sh script
```shell
<destinationPath>/deploy.sh -f deploy.properties
```


Create DNS record
---
### 1. If using an Azure hosted zone for DNS: Create an A record to point to Azure Load Balancer service resource
```shell
# For example when using example.com for the hosted DNS zone and dev.gis.example.com for the ArcGIS Enterprise FQDN:
# DNS_ZONE=example.com
# ARCGIS_SUBDOMAIN=dev.gis
DNS_ZONE=<DNSZoneName>
ARCGIS_SUBDOMAIN=<subdomain>
AZURE_LB_IP=$(kubectl get svc -n ${NAMESPACE} | grep LoadBalancer | awk '{print $4}')

az network dns record-set a add-record \
  --resource-group $RESOURCE_GROUP \
  --zone-name $DNS_ZONE \
  --record-set-name $ARCGIS_SUBDOMAIN \
  --ipv4-address $AZURE_LB_IP
```

### 2. If using external DNS provider: Create A record to point to Azure LB IP address
&emsp;a. Get Azure LB IP address
```shell
kubectl get svc -n ${NAMESPACE} | grep LoadBalancer | awk '{print $4}'
```

&emsp;b. Create A record in DNS provider console (map deployment FQDN to Azure Load Balancer IP address)


Create your ArcGIS Enterprise on Kubernetes organization
---
### 1. Create pod-placement-policies.json file

> [!NOTE]
> ArcGIS Enterprise's stateful data store components - the Relational Store, Object Store, In-Memory Store, and Spatiotemporal/Index Store - must run on the dedicated stateful NodePool created earlier. Without a placement policy, ArcGIS has no way to know that these components should be pinned to nodes with the `workload=stateful` taint; they would be scheduled on general-purpose nodes instead, defeating the isolation the stateful NodePool provides. The placement policy file passes node affinity rules and tolerations to the `configure.sh` script so these components land on the correct nodes from the moment the organization is created.

```json
{
    "placementPolicies": [
        {
            "placementPolicy": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "workload",
                                        "operator": "In",
                                        "values": [
                                            "stateful"
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                },
                "tolerations": [
                    {
                        "key": "workload",
                        "operator": "Equal",
                        "value": "stateful",
                        "effect": "NoSchedule"
                    }
                ]
            },
            "components": [
                "RELATIONAL",
                "BLOB",
                "IN_MEM_CACHE",
                "INDEXER",
                "QUEUE"
            ]
        }
    ]
}
```



### 2. Populate configure.properties file
Follow instructions from [Run the script](https://enterprise-k8s.arcgis.com/en/latest/deploy/create-a-new-organization.htm#ESRI_SECTION1_80617AFCB0B94C4A98406420F2E863C5) in _Create an organization_.

Note: `K8S_NAMESPACE` must match the `NAMESPACE` variable and `CONTEXT` must match the `SITE_CONTEXT` variable exported in the "Set session variables" step.

<details>
<summary>Example configure.properties file contents:</summary>
<br>

```yaml
# Configuration properties file for creating an Enterprise Organization.

# ------------------------------------
# ARCHITECTURE PROFILE
#
# Specify the availability and performance profiles you wish to use.
# ------------------------------------
#
# Availability Profiles
# ------------------------------------
# development
# standard
# enhanced
AVAILABILITY_PROFILE=""
# ------------------------------------
#
# Performance Profiles
# ------------------------------------
# standard
# enhanced
PERFORMANCE_PROFILE="standard"

# ------------------------------------
# SITENAME
# ------------------------------------
#
# Do not edit the following property
#
ARCGIS_SITENAME="${ARCGIS_SITENAME:-arcgis}"

# ------------------------------------
# ORGANIZATION PROPERTIES
#
# These values should match your deployment properties file.
# ------------------------------------
# The Kubernetes cluster namespace where ArcGIS Enterprise on Kubernetes will be deployed.
K8S_NAMESPACE=""

# The fully qualified domain name used to configure the ArcGIS Enterprise on
# Kubernetes organization. (Optional)
#
# By default, this value is extracted from the deployment properties for the
# site or set to a worker node FQDN and node port of the ingress controller
# service. If the site isn't accessible via one of those at the time of
# configuration, this property can be used to override the default behavior.
#ARCGIS_ENTERPRISE_FQDN=""

# ------------------------------------
# LICENSE PROPERTIES
#
# Enter the full path to the license file.
# ------------------------------------
LICENSE_FILE=""

# Specify the user type ID for the primary administrator.
# Examples of user type IDs along with their user type below:
#
# User type                   Type Id
# --------------------------|-----------------------
# Creator                   | creatorUT
# GIS Professional Basic    | GISProfessionalBasicUT
# GIS Professional Standard | GISProfessionalStdUT
# GIS Professional Advanced | GISProfessionalAdvUT
LICENSE_TYPE_ID="creatorUT"

# ------------------------------------
# ENCRYPTION KEYFILE
#
# The encryption keyfile is a plain text file used for AES-256 encryption/decryption
# of passwords. The contents of this file is arbitrary plain text and SHOULD NOT
# contain any passwords. This file should remain in a fixed location and the contents
# should not change.
#
# This is usually the same value specified in your deployment properties file.
ENCRYPTION_KEYFILE=""

# ------------------------------------
# ADMINISTRATOR ACCOUNT PROPERTIES
#
# ADMIN_USERNAME must be a minimum of 6 characters and can only contain the following,
# numbers 0-9, ASCII letters a-z, A-Z, at symbol (@), dash (-), period (.), and underscore (_).
#
# ADMIN_PASSWORD must be a minimum of 8 characters and must contain at least one letter
# (A-Z, a-z), one number (0-9) and a special character.
#
# NOTE: This password is AES-256 encrypted using the ENCRYPTION_KEYFILE specified above.
#
# To create an AES-256 encrypted password go to setup/tools/password-encrypt/ and run the command:
#
#    % ./password-encrypt.sh -f /path/to/keyfile.txt -p "my.registry.password"
#
# That command will output an encrypted string. Set ADMIN_PASSWORD to that encrypted value.
#
# ------------------------------------
ADMIN_USERNAME=""
ADMIN_PASSWORD=""
ADMIN_EMAIL=""
ADMIN_FIRST_NAME=""
ADMIN_LAST_NAME=""

# Specify the security question and answer for the primary administrator.
# Questions along with their indexes shown below:
#
# Index   Question
# ----- | -----------------------------------------------------
# 1     | What city were you born in?
# 2     | What was your high school mascot?
# 3     | What is your mother's maiden name?
# 4     | What was the make of your first car?
# 5     | What high school did you go to?
# 6     | What is the last name of your best friend?
# 7     | What is the middle name of your youngest sibling?
# 8     | What is the name of the street on which you grew up?
# 9     | What is the name of your favorite fictional character?
# 10    | What is the name of your favorite pet?
# 11    | What is the name of your favorite restaurant?
# 12    | What is the title of your favorite book?
# 13    | What is your dream job?
# 14    | Where did you go on your first date?

# Match this number with the questions above (between 1 and 14).
SECURITY_QUESTION_INDEX=
SECURITY_QUESTION_ANSWER=""

# ------------------------------------
# CLOUD CONFIG JSON FILENAME (Optional)
#
# Use one of these json templates in setup/templates/cloud-config to create
# a cloud configuration file which contains your configuration info:
#
#   aws-access-key.json.template
#   aws-iam-role.json.template
#   azure-storage-account-key.json.template
#   azure-system-assigned-identity.json.template
#   azure-user-assigned-identity.json.template
#   gcp-hmac-key.json.template
#
# Copy one these templates locally (remove the .template suffix) and add your
# cloud configuration info.
#
# Then set CLOUD_CONFIG_JSON_FILENAME to the full path of this file. This file
# can be deleted after a successful configure is completed.
#
# NOTE: When CLOUD_CONFIG_JSON_FILENAME is defined the values in the
# OBJECT_STORE_* storage properties below are ignored.
CLOUD_CONFIG_JSON_FILENAME=""

# ------------------------------------
# PLACEMENT POLICIES CONFIG FILENAME (Optional)
#
# Use one of these json templates in setup/templates/placement-policies to
# create a placement policy file which contains your configuration info:
#
#   placement-policies.json.template
#
# Copy one these templates locally (remove the .template suffix) and add your
# configuration info.
#
# Then set PLACEMENT_POLICIES_CONFIG_FILENAME to the full path of this file.
# This file can be deleted after a successful configure is completed.
#
# See the readme.md in setup/templates/placement-policies for more information.
PLACEMENT_POLICIES_CONFIG_FILENAME="pod-placement-policies.json"  # Give path to the pod-placement-policies.json file created above


# ------------------------------------
# LOG SETTINGS (Optional)
#
# Valid values:
#
#     SEVERE |  WARNING | INFO | FINE | VERBOSE | DEBUG
#
# The log level at which logs will be recorded during configuration.
# If no log level is specified, the default WARNING level will be used
# once the organization is configured. The log level can be changed
# after configuration using the edit operation.
#
# NOTE: Leave blank if you do not wish to change the log setting.
LOG_SETTING=""

# ------------------------------------
# LOG RETENTION MAX DAYS
#
# Number of days logs will be retained by the organization.
#
# Valid values:
#
#     An integer value between 1 and 999.
#
LOG_RETENTION_MAX_DAYS=60


# ------------------------------------
# STORAGE PROPERTIES
# ------------------------------------
#
# Storage type can be "STATIC" or "DYNAMIC". By default, the type is set to 
# DYNAMIC.
#
#  - For dynamic:
#     - Storage class names are mandatory and must already exist in the cluster.
#  - For static:
#     - Labels are mandatory.
#     - Persistent Volume Claims use label selectors (matchLabels).
#     - Persistent Volumes must match the label selector to be bound to the claim.
#
# - Size and type are mandatory for both static and dynamic storage.
# - Values are case sensitive.
# - For storage labels, use "key:value" syntax. For example:
#
#     label1: arcgis/tier:storage
#     label2: arcgis/app:postgres

# Relational Store
RELATIONAL_STORAGE_TYPE="DYNAMIC"
RELATIONAL_STORAGE_SIZE="16Gi"
RELATIONAL_STORAGE_CLASS="managed-premium"
RELATIONAL_STORAGE_LABEL_1="arcgis/tier=storage"
RELATIONAL_STORAGE_LABEL_2="arcgis/app=postgres"

# Object Store
OBJECT_STORAGE_TYPE="DYNAMIC"
OBJECT_STORAGE_SIZE="64Gi"
OBJECT_STORAGE_CLASS="managed-premium"
OBJECT_STORAGE_LABEL_1="arcgis/tier=storage"
OBJECT_STORAGE_LABEL_2="arcgis/app=ozone"

# In-Memory Store
MEMORY_STORAGE_TYPE="DYNAMIC"
MEMORY_STORAGE_SIZE="16Gi"
MEMORY_STORAGE_CLASS="managed-premium"
MEMORY_STORAGE_LABEL_1="arcgis/tier=storage"
MEMORY_STORAGE_LABEL_2="arcgis/app=ignite"

# Queue Store
QUEUE_STORAGE_TYPE="DYNAMIC"
QUEUE_STORAGE_SIZE="16Gi"
QUEUE_STORAGE_CLASS="managed-premium"
QUEUE_STORAGE_LABEL_1="arcgis/tier=queue"
QUEUE_STORAGE_LABEL_2="arcgis/app=rabbitmq"

# Spatiotemporal and Index Store
INDEXER_STORAGE_TYPE="DYNAMIC"
INDEXER_STORAGE_SIZE="16Gi"
INDEXER_STORAGE_CLASS="managed-premium"
INDEXER_STORAGE_LABEL_1="arcgis/tier=storage"
INDEXER_STORAGE_LABEL_2="arcgis/app=elasticsearch"

# Item Packages
SHARING_STORAGE_TYPE="DYNAMIC"
SHARING_STORAGE_SIZE="16Gi"
SHARING_STORAGE_CLASS="managed-premium"
SHARING_STORAGE_LABEL_1="arcgis/tier=api"
SHARING_STORAGE_LABEL_2="arcgis/app=sharing"

# Prometheus (metrics api)
PROMETHEUS_STORAGE_TYPE="DYNAMIC"
PROMETHEUS_STORAGE_SIZE="30Gi"
PROMETHEUS_STORAGE_CLASS="managed-premium"
PROMETHEUS_STORAGE_LABEL_1="arcgis/tier=api"
PROMETHEUS_STORAGE_LABEL_2="arcgis/app=prometheus"

# END
```
</details>

### 2. Run configure.sh script
```shell
<destinationPath>/tools/configure/configure.sh -f configure.properties
```


Access your ArcGIS Enterprise on Kubernetes organization
---
### 1. Get organization base URL
```shell
kubectl get secret arcgis-env-variables -n ${NAMESPACE} -o json | jq -r '.data["env-variables.json"]' | base64 -d | jq -r '.ROOT_ORG_BASE_URL'
```

&emsp;&emsp;Example output: `https://<DNSAlias>/<context>/`

&emsp;&emsp;Copy output into a browser and append any of the exposed applications (i.e. manager, admin, home, rest/services, etc.)


Verify the cluster
---
### 1. Verify node scheduling resources
```shell
kubectl get aksnodeclass
kubectl get nodepools
kubectl get nodeclaims
```

### 2. Watch nodes join the cluster
```shell
kubectl get nodes -w
```

### 3. Verify system pods
```shell
kubectl get pods -n kube-system
```

Teardown
---
Use the following steps to delete all resources created by this guide. Deleting the resource group removes all associated Azure resources, including the AKS cluster.

### 1. Delete the resource group
```shell
az group delete \
  --name $RESOURCE_GROUP \
  --yes \
  --no-wait
```

&emsp;&emsp;Reference: https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-cli
