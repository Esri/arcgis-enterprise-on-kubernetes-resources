<!--
# Copyright 2025 Esri
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

Deploy ArcGIS Enterprise on Kubernetes on Google Kubernetes Engine
===
Table of contents
---
  * [Introduction](#introduction)
  * [Prepare the client workstation](#prepare-the-client-workstation)
  * [Create a GKE cluster](#create-a-google-kubernetes-engine-cluster)
  * [Deploy ArcGIS Enterprise on Kubernetes](#deploy-arcgis-enterprise-on-kubernetes)
  * [Create DNS record](#create-dns-record)
  * [Create your ArcGIS Enterprise on Kubernetes organization](#create-your-arcgis-enterprise-on-kubernetes-organization)
  * [Access your ArcGIS Enterprise on Kubernetes organization](#access-your-arcgis-enterprise-on-kubernetes-organization)

Introduction
---
The following will provide guidance on setting up a client workstation, provisioning and connecting to a GKE cluster, and deploying ArcGIS Enterprise on Kubernetes.
 
The cluster’s Kubernetes version will be 1.30.x (the latest supported 1.30 release) and consist of 6 nodes to support the enhanced availability architecture profile with additional capacity for publishing dedicated services. A load balancer will handle ingress from the internet to the bundled ingress controller. Google's Cloud DNS service is the DNS provider used as an example in this guide, but any provider can instead be manually configured when you create the DNS record.
 
The commands provided in this guide may need to be modified to meet your organizational needs. Placeholders, denoted as <variable\>, must be replaced with the relevant deployment information prior to running the command.


Prepare the client workstation
---
### 1. Install kubectl
&emsp;a. Download kubectl
```shell
curl -LO https://dl.k8s.io/release/v1.30.9/bin/linux/amd64/kubectl
```

&emsp;b. Add executable permissions and move to location on path
```shell
chmod +x kubectl && \
sudo mv kubectl /usr/local/bin/
```

&emsp;&emsp;Reference: https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/

### 2. Install and configure gcloud CLI (requires Python version 3.8-3.13)
&emsp;a. Install gcloud CLI
```shell
curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz
tar -xf google-cloud-cli-linux-x86_64.tar.gz
./google-cloud-sdk/install.sh
gcloud components install gke-gcloud-auth-plugin
```

&emsp;&emsp;Reference: https://cloud.google.com/sdk/docs/install and https://cloud.google.com/blog/products/containers-kubernetes/kubectl-auth-changes-in-gke

&emsp;b. Confirm installation and configure gcloud CLI
```shell
gcloud --version
gcloud init
```

&emsp;&emsp;Reference: https://cloud.google.com/sdk/docs/install

### 3. Download ArcGIS Enterprise on Kubernetes deployment scripts and locate license file
&emsp;a. Sign in to My Esri and download deployment scripts and license file  
&emsp;b. Extract deployment scripts
```shell
tar zxf ArcGIS_Enterprise_Kubernetes_*.tar.gz -C <destinationPath>
```

Create a Google Kubernetes engine cluster
---
### 1. Create cluster
```shell
CLUSTER_NAME=<clusterName>
REGION=<region>
gcloud container clusters create $CLUSTER_NAME --cluster-version=1.30 --location=$REGION --enable-network-policy --node-locations=$REGION-a --num-nodes=6 --machine-type=e2-standard-8
```

&emsp;&emsp;Reference: https://cloud.google.com/sdk/gcloud/reference/container/clusters/create

### 2. Create storage class (optional, for use with system managed backup store)
```shell
cat << EOF | kubectl apply -f -
allowVolumeExpansion: true
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  annotations:
    components.gke.io/component-name: pdcsi
    components.gke.io/component-version: 0.14.5
    components.gke.io/layer: addon
  labels:
    addonmanager.kubernetes.io/mode: EnsureExists
    k8s-app: gcp-compute-persistent-disk-csi-driver
  name: premium-rwo-retain
parameters:
  type: pd-ssd
provisioner: pd.csi.storage.gke.io
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
EOF
```

&emsp;&emsp;Reference: https://cloud.google.com/kubernetes-engine/docs/concepts/storage-overview

### 3. Create application namespace
```shell
kubectl create namespace arcgis
```

Deploy ArcGIS Enterprise on Kubernetes
---
### 1. Populate deploy.properties file
Follow instructions from [Run the deployment script in silent mode](https://enterprise-k8s.arcgis.com/en/latest/deploy/run-the-deployment-script.htm#ESRI_SECTION1_930D8184D9E9480BB679ABED1743A8CE) in _Run the deployment script_.

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
#
LOAD_BALANCER_TYPE="gcp-external"
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
VERSION_TAG="${VERSION_TAG:-11.4.0.6285}"

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

# If your Kubernetes cluster has a domain name other than cluster.local, use this
# property to specify the domain name
K8S_CLUSTER_DOMAIN="${K8S_CLUSTER_DOMAIN:-cluster.local}"

# If you are deploying ArcGIS Enterprise on Kubernetes and your
# Kubernetes cluster spans three or more availability zones, update
# 'kubernetes.io/hostname' to 'topology.kubernetes.io/zone'
K8S_AVAILABILITY_TOPOLOGY_KEY="kubernetes.io/hostname"

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
### 1. If using Google's Cloud DNS service for DNS: Create A record to point to LB service resource (requires a previously configured hosted zone)
```shell
DNS_Alias=$(kubectl get secret arcgis-env-variables -n arcgis -o json | jq -r '.data["env-variables.json"]' | base64 -d | jq -r
'.ARCGIS_ENTERPRISE_FQDN')
LB_IP=$(kubectl get svc -n arcgis | grep LoadBalancer | awk '{print $4}')
gcloud dns record-sets create $DNS_Alias --rrdatas=$LB_IP --type=A --ttl=60 --zone=<zoneName>
```

### 2. If using external DNS provider: Create CNAME record to point to Load Balancer IP address
&emsp;a. Get LB IP address
```shell
kubectl get svc -n arcgis | grep LoadBalancer | awk '{print $4}'
```

&emsp;b. Create CNAME record in DNS provider console (map deployment FQDN to LB IP address)

Create your ArcGIS Enterprise on Kubernetes organization
---
### 1. Populate configure.properties file
Follow instructions from [Run the script](https://enterprise-k8s.arcgis.com/en/latest/deploy/create-a-new-organization.htm#ESRI_SECTION1_80617AFCB0B94C4A98406420F2E863C5) in _Create an organization_.

<details>
<summary>Example configure.properties file contents:</summary>
<br>
 
```yaml
# Configuration properties file for creating an Enterprise Organization.

# ------------------------------------
# ARCHITECTURE PROFILE
#
# Specify the deployment profile you wish to use.
# ------------------------------------
#
# Profiles
# ------------------------------------
# development
# standard-availability
# enhanced-availability
SYSTEM_ARCH_PROFILE="enhanced-availability"

# ------------------------------------
# ORGANIZATION PROPERTIES
#
# These values should match your deployment properties file.
# ------------------------------------
# The Kubernetes cluster namespace where ArcGIS Enterprise on Kubernetes will be deployed.
K8S_NAMESPACE="arcgis"
# Enter the context path to be used in the URL for ArcGIS Enterprise on Kubernetes.
# For example, the context path of 'https://<FQDN>/arcgis/admin' would be 'arcgis'.
CONTEXT="arcgis"
# The fully qualified domain name to access ArcGIS Enterprise on Kubernetes.
ARCGIS_ENTERPRISE_FQDN="arcgis"

# ------------------------------------
# LICENSE PROPERTIES
#
# Enter the full path to the license file.
# ------------------------------------
LICENSE_FILE="/data/k8s/114_Kubernetes_License.json"

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
ENCRYPTION_KEYFILE="/data/k8s/keyfile.txt"

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
ADMIN_USERNAME="administrator"
ADMIN_PASSWORD="U2FsdGVkX1/+Mbm4XEYObOarXyXrDJlPvdwGsnsMSAxMjk6xnIMBU/4HuZOXIKXy"
ADMIN_EMAIL="administrator@organization.com"
ADMIN_FIRST_NAME="Site"
ADMIN_LAST_NAME="Admin"

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
SECURITY_QUESTION_INDEX=2
SECURITY_QUESTION_ANSWER="Globie"

# ------------------------------------
# FOLDER PATHS (Optional)
#
# Root folder paths for data stores. Registering folder paths during site
# creation allows you to avoid disruptions that typically occur when registering
# folder paths after the organization has been configured.
#
# You can provide the folder paths you wish to register in a .json file.
#
# For a sample JSON, refer to this file:
#
#     tools/configure/sample_data_folder_paths.json
#
# To configure your organization with your defined folder paths use the -u flag:
#
#     % ./configure.sh -f my.properties -u /path/to/my_data_folder_paths.json
#
# NOTE: REGISTERED_FOLDER_PATHS="/folder/path1,/folder/path2, etc..." is a
# legacy variable. This variable is no longer recommended for use.
REGISTERED_FOLDER_PATHS=""

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
RELATIONAL_STORAGE_CLASS="premium-rwo"
RELATIONAL_STORAGE_LABEL_1="arcgis/tier=storage"
RELATIONAL_STORAGE_LABEL_2="arcgis/app=postgres"

# Object Store
OBJECT_STORAGE_TYPE="DYNAMIC"
OBJECT_STORAGE_SIZE="64Gi"
OBJECT_STORAGE_CLASS="premium-rwo"
OBJECT_STORAGE_LABEL_1="arcgis/tier=storage"
OBJECT_STORAGE_LABEL_2="arcgis/app=ozone"

# In-Memory Store
MEMORY_STORAGE_TYPE="DYNAMIC"
MEMORY_STORAGE_SIZE="16Gi"
MEMORY_STORAGE_CLASS="premium-rwo"
MEMORY_STORAGE_LABEL_1="arcgis/tier=storage"
MEMORY_STORAGE_LABEL_2="arcgis/app=ignite"

# Queue Store
QUEUE_STORAGE_TYPE="DYNAMIC"
QUEUE_STORAGE_SIZE="16Gi"
QUEUE_STORAGE_CLASS="premium-rwo"
QUEUE_STORAGE_LABEL_1="arcgis/tier=queue"
QUEUE_STORAGE_LABEL_2="arcgis/app=rabbitmq"

# Spatiotemporal and Index Store
INDEXER_STORAGE_TYPE="DYNAMIC"
INDEXER_STORAGE_SIZE="150Gi"
INDEXER_STORAGE_CLASS="premium-rwo"
INDEXER_STORAGE_LABEL_1="arcgis/tier=storage"
INDEXER_STORAGE_LABEL_2="arcgis/app=elasticsearch"

# Item Packages
SHARING_STORAGE_TYPE="DYNAMIC"
SHARING_STORAGE_SIZE="16Gi"
SHARING_STORAGE_CLASS="premium-rwo"
SHARING_STORAGE_LABEL_1="arcgis/tier=api"
SHARING_STORAGE_LABEL_2="arcgis/app=sharing"

# Prometheus (metrics api)
PROMETHEUS_STORAGE_TYPE="DYNAMIC"
PROMETHEUS_STORAGE_SIZE="30Gi"
PROMETHEUS_STORAGE_CLASS="premium-rwo"
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
kubectl get secret arcgis-env-variables -n arcgis -o json | jq -r '.data["env-variables.json"]' | base64 -d | jq -r '.ROOT_ORG_BASE_URL'
```

&emsp;&emsp;Example output: `https://<DNSAlias>/<context>/`

&emsp;&emsp;Copy output into a browser and append any of the exposed applications (i.e. manager, admin, home, rest/services, etc.)
