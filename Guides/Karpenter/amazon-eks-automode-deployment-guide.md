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

Deploy ArcGIS Enterprise on Kubernetes on Amazon EKS Auto Mode
===
Table of contents
---
  * [Introduction](#introduction)
  * [Prepare the client workstation](#prepare-the-client-workstation)
  * [Create an Amazon EKS cluster](#create-an-amazon-eks-cluster)
  * [Enable Auto Mode](#enable-auto-mode)
  * [Install cluster dependencies](#install-cluster-dependencies)
  * [Deploy ArcGIS Enterprise on Kubernetes](#deploy-arcgis-enterprise-on-kubernetes)
  * [Create DNS record](#create-dns-record)
  * [Create your ArcGIS Enterprise on Kubernetes organization](#create-your-arcgis-enterprise-on-kubernetes-organization)
  * [Access your ArcGIS Enterprise on Kubernetes organization](#access-your-arcgis-enterprise-on-kubernetes-organization)
  * [Verify the cluster](#verify-the-cluster)
  * [Teardown](#teardown)

Introduction
---
The following will provide guidance on setting up a client workstation, provisioning an Amazon EKS Auto Mode cluster, and deploying ArcGIS Enterprise on Kubernetes.

EKS Auto Mode automates compute provisioning using Karpenter-based NodePools, replacing the fixed node groups used in the standard EKS deployment. A network load balancer handles ingress using the AWS Load Balancer Controller, and Pod Identity Associations are used to grant AWS credentials to system and ArcGIS workloads.

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

### 2. Install and configure AWS CLI
&emsp;a. Install AWS CLI
```shell
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
unzip awscliv2.zip && \
sudo ./aws/install && \
rm -f awscliv2.zip
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

&emsp;b. Confirm installation and configure AWS CLI (use `json` for default output format)
```shell
aws --version
aws configure
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-user.html

### 3. Install Helm v3
```shell
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
sudo chmod 700 get_helm.sh
./get_helm.sh
rm -f get_helm.sh
```

&emsp;&emsp;Reference: https://helm.sh/docs/intro/install/


### 4. Download ArcGIS Enterprise on Kubernetes deployment scripts and locate license file
&emsp;a. Sign in to My Esri and download deployment scripts and license file  
&emsp;b. Extract deployment scripts
```shell
tar zxf ArcGIS_Enterprise_Kubernetes_*.tar.gz -C <destinationPath>
```

### 5. Set session variables
First, list available VPCs to identify the one you want to deploy into:
```shell
aws ec2 describe-vpcs \
  --query 'Vpcs[*].{VpcId:VpcId,CidrBlock:CidrBlock,Name:Tags[?Key==`Name`]|[0].Value}' \
  --output table
```

Then set all variables:
```shell
export CLUSTER_NAME="<cluster-name>"
export AWS_REGION="<region>"
export K8S_VERSION="<k8s-version>"
export VPC_ID="<vpc-id>"
export NAMESPACE="<k8s-namespace-for-arcgis>"
export SITE_CONTEXT="<site-context-for-arcgis>"
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
echo "Account ID: ${AWS_ACCOUNT_ID}"
```

### 6. Create required IAM roles
The following IAM roles must exist in your AWS account before provisioning the cluster. EKS Auto Mode uses Pod Identity Associations, requiring dedicated roles for the EBS CSI driver, VPC CNI plugin, and ArcGIS workloads.

&emsp;a. Create the EBS CSI Driver Pod Identity role
```shell
aws iam create-role \
  --role-name AmazonEKSPodIdentityAmazonEBSCSIDriverRole-${CLUSTER_NAME} \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"Service": "pods.eks.amazonaws.com"},
        "Action": ["sts:AssumeRole", "sts:TagSession"]
      }
    ]
  }'

aws iam attach-role-policy \
  --role-name AmazonEKSPodIdentityAmazonEBSCSIDriverRole-${CLUSTER_NAME} \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy
```

&emsp;b. Create the VPC CNI Pod Identity role
```shell
aws iam create-role \
  --role-name AmazonEKSPodIdentityAmazonVPCCNIRole-${CLUSTER_NAME} \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"Service": "pods.eks.amazonaws.com"},
        "Action": ["sts:AssumeRole", "sts:TagSession"]
      }
    ]
  }'

aws iam attach-role-policy \
  --role-name AmazonEKSPodIdentityAmazonVPCCNIRole-${CLUSTER_NAME} \
  --policy-arn arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy
```

>[!NOTE]
> Follow the steps mentioned <linkPlaceholder> to create the ArcGIS Pod Identity role only if you plan to use AWS services such as S3 for your ArcGIS deployment. If your deployment does not require AWS service access, you can skip step.

Create an Amazon EKS cluster
---
EKS Auto Mode requires dedicated IAM roles for the cluster control plane and nodes, a cluster security group, and explicit subnet selection. These replace the simpler `eksctl create cluster` workflow used in the standard EKS deployment.

### 1. Create the IAM cluster role
&emsp;a. Create the role
```shell
aws iam create-role \
  --role-name eks-automode-cluster-role-${CLUSTER_NAME} \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"Service": "eks.amazonaws.com"},
        "Action": ["sts:AssumeRole", "sts:TagSession"]
      }
    ]
  }'
```

&emsp;b. Attach required managed policies
```shell
for POLICY_ARN in \
  "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSBlockStoragePolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSComputePolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSLoadBalancingPolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSNetworkingPolicy"; do
  aws iam attach-role-policy \
    --role-name eks-automode-cluster-role-${CLUSTER_NAME} \
    --policy-arn "$POLICY_ARN"
done
```

&emsp;c. Store the role ARN
```shell
CLUSTER_ROLE_ARN=$(aws iam get-role \
  --role-name eks-automode-cluster-role-${CLUSTER_NAME} \
  --query 'Role.Arn' \
  --output text)

echo "Cluster Role ARN: ${CLUSTER_ROLE_ARN}"
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/eks/latest/userguide/cluster-iam-role.html

### 2. Create the IAM node role
&emsp;a. Create the role
```shell
aws iam create-role \
  --role-name eks-automode-node-role-${CLUSTER_NAME} \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }
    ]
  }'
```

&emsp;b. Attach required managed policies
```shell
for POLICY_ARN in \
  "arn:aws:iam::aws:policy/AmazonEKSWorkerNodeMinimalPolicy" \
  "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"; do
  aws iam attach-role-policy \
    --role-name eks-automode-node-role-${CLUSTER_NAME} \
    --policy-arn "$POLICY_ARN"
done
```

&emsp;c. Store the role ARN
```shell
NODE_ROLE_NAME=$(aws iam get-role \
  --role-name eks-automode-node-role-${CLUSTER_NAME} \
  --query 'Role.RoleName' \
  --output text)

echo "Node Role Name: ${NODE_ROLE_NAME}"
```

### 3. Create the cluster security group
&emsp;a. Retrieve the VPC CIDR block
```shell
VPC_CIDR=$(aws ec2 describe-vpcs \
  --vpc-ids ${VPC_ID} \
  --query 'Vpcs[0].CidrBlock' \
  --output text)

echo "VPC CIDR: ${VPC_CIDR}"
```

&emsp;b. Create the security group
```shell
CLUSTER_SG_ID=$(aws ec2 create-security-group \
  --group-name eks-automode-sg-${CLUSTER_NAME} \
  --description "Security group for EKS Auto Mode Cluster ${CLUSTER_NAME}" \
  --vpc-id ${VPC_ID} \
  --query 'GroupId' \
  --output text)

echo "Security Group ID: ${CLUSTER_SG_ID}"
```

&emsp;c. Add inbound rule to allow all traffic from within the VPC
```shell
aws ec2 authorize-security-group-ingress \
  --group-id ${CLUSTER_SG_ID} \
  --protocol -1 \
  --cidr ${VPC_CIDR}
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/vpc/latest/userguide/security-groups.html

### 4. Identify subnets
List the subnets for your VPC to identify the subnet IDs to use when creating the cluster:
```shell
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --query 'Subnets[*].{SubnetId:SubnetId,AZ:AvailabilityZone,CIDR:CidrBlock,Public:MapPublicIpOnLaunch,Name:Tags[?Key==`Name`]|[0].Value}' \
  --output table
```

### 5. Provision Amazon EKS Auto Mode cluster
Provide at least two subnet IDs in different Availability Zones. Replace the subnet IDs with values retrieved in the previous step:
```shell
aws eks create-cluster \
    --name ${CLUSTER_NAME} \
    --region ${AWS_REGION} \
    --kubernetes-version ${K8S_VERSION} \
    --role-arn ${CLUSTER_ROLE_ARN} \
    --resources-vpc-config '{
    "subnetIds": [
        "<subnet-id-1>",
        "<subnet-id-2>",
        "<subnet-id-3>"
    ],
    "securityGroupIds": [
        "'"${CLUSTER_SG_ID}"'"
    ],
    "endpointPublicAccess": true,
    "endpointPrivateAccess": true
    }' \
    --compute-config '{
    "enabled": true
    }' \
    --storage-config '{
    "blockStorage": {
        "enabled": true
    }
    }' \
    --kubernetes-network-config '{
    "elasticLoadBalancing": {
        "enabled": true
    }
    }' \
    --access-config authenticationMode=API_AND_CONFIG_MAP
```

Wait for the cluster to become active (typically 15-20 minutes):
```shell
aws eks wait cluster-active \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION}
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/eks/latest/userguide/automode.html

### 6. Update kubeconfig
```shell
aws eks update-kubeconfig \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION} \
  --alias ${CLUSTER_NAME}
```

### 7. Retrieve cluster security group and subnets
Store these values in shell variables for use when creating the NodeClass:
```shell
CLUSTER_SG=$(aws eks describe-cluster \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION} \
  --query 'cluster.resourcesVpcConfig.clusterSecurityGroupId' \
  --output text)

echo "Cluster Security Group: ${CLUSTER_SG}"
```

```shell
SUBNET_IDS=$(aws eks describe-cluster \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION} \
  --query 'cluster.resourcesVpcConfig.subnetIds' \
  --output text)

echo "Cluster Subnets: ${SUBNET_IDS}"
```


Enable Auto Mode
---
When the cluster is created with `compute-config enabled=true`, Auto Mode compute is technically active but no capacity will be launched until a NodeClass and NodePools are defined. Two additional steps are needed: confirming all Auto Mode capabilities are active, and granting the node role access to join the cluster.

### 1. Verify Auto Mode is enabled
Confirm that compute, block storage, and elastic load balancing are all active:
```shell
aws eks describe-cluster \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION} \
  --query '{Compute: cluster.computeConfig.enabled, BlockStorage: cluster.storageConfig.blockStorage.enabled, LoadBalancing: cluster.kubernetesNetworkConfig.elasticLoadBalancing.enabled}'
```
>[!NOTE]
> All three values should return `true`. If any are `false`, re-run the update command:

```shell
aws eks update-cluster-config \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION} \
  --compute-config '{
    "enabled": true
  }' \
  --storage-config '{
    "blockStorage": {
      "enabled": true
    }
  }' \
  --kubernetes-network-config '{
    "elasticLoadBalancing": {
      "enabled": true
    }
  }'
```

Wait for the cluster to return to `ACTIVE`:
```shell
aws eks wait cluster-active \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION}
```

### 2. Create the node role access entry
Auto Mode nodes use `eks-automode-node-role-${CLUSTER_NAME}` to join the cluster. Create an access entry for this role if one does not already exist:
```shell
aws eks create-access-entry \
  --cluster-name ${CLUSTER_NAME} \
  --principal-arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/eks-automode-node-role-${CLUSTER_NAME} \
  --type EC2 \
  --region ${AWS_REGION}
```

Associate the `AmazonEKSAutoNodePolicy`:
```shell
aws eks associate-access-policy \
  --cluster-name ${CLUSTER_NAME} \
  --principal-arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/eks-automode-node-role-${CLUSTER_NAME} \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSAutoNodePolicy \
  --access-scope type=cluster \
  --region ${AWS_REGION}
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/eks/latest/userguide/automode.html


Install cluster dependencies
---
### 1. Configure node scheduling
EKS Auto Mode uses a NodeClass and NodePools to control how workload nodes are provisioned, replacing fixed managed node groups.

> [!IMPORTANT]
> - Seperate NodePools should be used for stateful data store workloads to ensure proper isolation and scheduling using labels and taints.
> - A dedicated NodePool should be used for GPU-accelerated workloads with appropriate instance type requirements and taints to prevent scheduling non-GPU workloads there.
> - All NodePools must have limits defined to prevent unbounded node provisioning.
> - Disruption budgets should be configured to control how and when nodes can be consolidated or deprovisioned.


&emsp;a. Prepare subnet YAML from the subnet IDs retrieved earlier
```shell
SUBNET_YAML=$(for s in ${SUBNET_IDS}; do echo "    - id: $s"; done)
```

&emsp;b. Apply the NodeClass
```shell
cat << EOF | kubectl apply -f -
apiVersion: eks.amazonaws.com/v1
kind: NodeClass
metadata:
  name: eks-auto
  labels:
    app.kubernetes.io/managed-by: eks
  finalizers:
    - eks.amazonaws.com/termination
spec:
  role: ${NODE_ROLE_NAME}
  ephemeralStorage:
    size: 300Gi
    iops: 3000
    throughput: 125
  securityGroupSelectorTerms:
    - id: ${CLUSTER_SG}
  subnetSelectorTerms:
${SUBNET_YAML}
  networkPolicy: DefaultAllow
  networkPolicyEventLogs: Disabled
  snatPolicy: Random
EOF
```

&emsp;c. Apply NodePools for each workload type. General-Purpose NodePool for generic ArcGIS workloads:
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
        group: eks.amazonaws.com
        kind: NodeClass
        name: eks-auto
      requirements:             # Use requirements to control which instance types Karpenter can provision for this NodePool. Adjust values based on workload needs and expected demand patterns.
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: kubernetes.io/os
          operator: In
          values: ["linux"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: eks.amazonaws.com/instance-family
          operator: In
          values: ["m5a"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["m5a.2xlarge"]
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
        group: eks.amazonaws.com
        kind: NodeClass
        name: eks-auto
      taints:
        - key: workload
          value: stateful
          effect: NoSchedule
      requirements:             # Use requirements to control which instance types Karpenter can provision for this NodePool. Adjust values based on workload needs and expected demand patterns.
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
        - key: kubernetes.io/os
          operator: In
          values: ["linux"]
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: eks.amazonaws.com/instance-family
          operator: In
          values: ["m5a"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["m5a.2xlarge"]
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
        group: eks.amazonaws.com
        kind: NodeClass
        name: eks-auto
      taints:
        - key: nvidia.com/gpu
          effect: NoSchedule
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
        - key: eks.amazonaws.com/instance-family
          operator: In
          values: ["g4dn", "g5"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["g4dn.2xlarge"]
        - key: eks.amazonaws.com/instance-gpu-count
          operator: In
          values: ["1"]
        - key: eks.amazonaws.com/instance-gpu-manufacturer
          operator: In
          values: ["nvidia"]
        - key: nvidia.com/gpu
          operator: Exists
  limits:                        # Set limits to prevent overprovisioning - adjust values based on expected workload demand
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

&emsp;&emsp;Critical Addons NodePool for system-critical components such as CoreDNS, EBS CSI controller, metrics-server, and the AWS Load Balancer Controller:
```shell
cat << EOF | kubectl apply -f -
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: critical-addons
  labels:
    app.kubernetes.io/managed-by: eks
  annotations:
    kubernetes.io/description: "NodePool for critical system addons"
spec:
  template:
    spec:
      nodeClassRef:
        group: eks.amazonaws.com
        kind: NodeClass
        name: eks-auto
      taints:
        - key: CriticalAddonsOnly
          effect: NoSchedule
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["on-demand"]
        - key: eks.amazonaws.com/instance-category
          operator: In
          values: ["c", "m", "r"]
        - key: eks.amazonaws.com/instance-generation
          operator: Gt
          values: ["4"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64", "arm64"]
        - key: kubernetes.io/os
          operator: In
          values: ["linux"]
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 30s
    budgets:
    - nodes: "10%"             
EOF
```

&emsp;&emsp;Reference: https://karpenter.sh/docs/concepts/nodepools/

### 2. Configure pod identity
Auto Mode nodes have IMDS disabled, which means pods cannot use the node instance profile for AWS credentials. Pod Identity Associations must be created before installing add-ons so that credentials are available when addon pods start.

&emsp;a. Create associations for the EBS CSI driver controller and VPC CNI plugin
```shell
# EBS CSI Driver
aws eks create-pod-identity-association \
  --cluster-name ${CLUSTER_NAME} \
  --namespace kube-system \
  --service-account ebs-csi-controller-sa \
  --role-arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/AmazonEKSPodIdentityAmazonEBSCSIDriverRole-${CLUSTER_NAME} \
  --region ${AWS_REGION}

# VPC CNI
aws eks create-pod-identity-association \
  --cluster-name ${CLUSTER_NAME} \
  --namespace kube-system \
  --service-account aws-node \
  --role-arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/AmazonEKSPodIdentityAmazonVPCCNIRole-${CLUSTER_NAME} \
  --region ${AWS_REGION}
```
&emsp;&emsp;Reference: https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html


&emsp;b. Create the application namespace
```shell
kubectl create namespace ${NAMESPACE}
```

### 3. Install EKS add-ons
Install the following add-ons at the latest default version for your cluster's Kubernetes version. Add-ons that run as Deployments are pinned to the `critical-addons` NodePool; DaemonSets run on all nodes automatically.

| Add-on | Type | Placement |
|---|---|---|
| `vpc-cni` | DaemonSet | All nodes |
| `coredns` | Deployment | `critical-addons` NodePool |
| `kube-proxy` | DaemonSet | All nodes |
| `aws-ebs-csi-driver` | Deployment + DaemonSet | Controller -> `critical-addons` |
| `eks-pod-identity-agent` | DaemonSet | All nodes |
| `metrics-server` | Deployment | `critical-addons` NodePool |

&emsp;a. Install DaemonSet add-ons
```shell
for ADDON in vpc-cni kube-proxy eks-pod-identity-agent; do
  aws eks create-addon \
    --cluster-name ${CLUSTER_NAME} \
    --addon-name "$ADDON" \
    --resolve-conflicts OVERWRITE \
    --region ${AWS_REGION}
done
```

&emsp;b. Install CoreDNS
```shell
aws eks create-addon \
  --cluster-name ${CLUSTER_NAME} \
  --addon-name coredns \
  --configuration-values '{"nodeSelector":{"karpenter.sh/nodepool":"critical-addons"},"tolerations":[{"key":"CriticalAddonsOnly","operator":"Exists","effect":"NoSchedule"}]}' \
  --resolve-conflicts OVERWRITE \
  --region ${AWS_REGION}
```

&emsp;c. Install Metrics Server
```shell
aws eks create-addon \
  --cluster-name ${CLUSTER_NAME} \
  --addon-name metrics-server \
  --configuration-values '{"nodeSelector":{"karpenter.sh/nodepool":"critical-addons"},"tolerations":[{"key":"CriticalAddonsOnly","operator":"Exists","effect":"NoSchedule"}]}' \
  --resolve-conflicts OVERWRITE \
  --region ${AWS_REGION}
```

&emsp;d. Install EBS CSI Driver
```shell
aws eks create-addon \
  --cluster-name ${CLUSTER_NAME} \
  --addon-name aws-ebs-csi-driver \
  --configuration-values '{"controller":{"nodeSelector":{"karpenter.sh/nodepool":"critical-addons"},"tolerations":[{"key":"CriticalAddonsOnly","operator":"Exists"}]},"node":{"tolerations":[{"key":"CriticalAddonsOnly","operator":"Exists"}]}}' \
  --resolve-conflicts OVERWRITE \
  --region ${AWS_REGION}
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/eks/latest/userguide/eks-add-ons.html

### 4. Install AWS Load Balancer Controller
The AWS Load Balancer Controller manages ALBs and NLBs for Kubernetes Ingress and Service resources. It is installed via Helm, uses EKS Pod Identity for AWS credentials, and is pinned to the `critical-addons` NodePool.

&emsp;a. Tag subnets for ELB discovery. The controller discovers subnets through tags. For public subnets (used for internet-facing load balancers):
```shell
for SUBNET_ID in ${SUBNET_IDS}; do
  aws ec2 create-tags \
    --region ${AWS_REGION} \
    --resources ${SUBNET_ID} \
    --tags \
      Key=kubernetes.io/role/elb,Value=1 \
    Key=kubernetes.io/cluster/${CLUSTER_NAME},Value=shared
done
```

&emsp;&emsp;For private subnets (used for internal load balancers):
```shell
for SUBNET_ID in ${SUBNET_IDS}; do
  aws ec2 create-tags \
    --region ${AWS_REGION} \
    --resources ${SUBNET_ID} \
    --tags \
      Key=kubernetes.io/role/internal-elb,Value=1 \
      Key=kubernetes.io/cluster/${CLUSTER_NAME},Value=shared
done
```

&emsp;b. Download the IAM policy and create it in your account
```shell
curl -sS -o /tmp/lb-iam-policy.json \
  https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json

aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy-${CLUSTER_NAME} \
  --policy-document file:///tmp/lb-iam-policy.json
```

&emsp;c. Create a Pod Identity IAM role for the controller
```shell
aws iam create-role \
  --role-name AmazonEKSPodIdentityAWSLoadBalancerControllerRole-${CLUSTER_NAME} \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"Service": "pods.eks.amazonaws.com"},
        "Action": ["sts:AssumeRole", "sts:TagSession"]
      }
    ]
  }'

aws iam attach-role-policy \
  --role-name AmazonEKSPodIdentityAWSLoadBalancerControllerRole-${CLUSTER_NAME} \
  --policy-arn arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy-${CLUSTER_NAME}
```

&emsp;d. Create the Kubernetes service account and Pod Identity association
```shell
kubectl create serviceaccount aws-load-balancer-controller -n kube-system --dry-run=client -o yaml | kubectl apply -f -

aws eks create-pod-identity-association \
  --cluster-name ${CLUSTER_NAME} \
  --namespace kube-system \
  --service-account aws-load-balancer-controller \
  --role-arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/AmazonEKSPodIdentityAWSLoadBalancerControllerRole-${CLUSTER_NAME} \
  --region ${AWS_REGION}
```

&emsp;e. Add the EKS Helm repository and install the controller
```shell
helm repo add eks https://aws.github.io/eks-charts && \
helm repo update
```

```shell
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=${CLUSTER_NAME} \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set region=${AWS_REGION} \
  --set vpcId=${VPC_ID} \
  --set nodeSelector."karpenter\.sh/nodepool"=critical-addons \
  --set "tolerations[0].key=CriticalAddonsOnly" \
  --set "tolerations[0].operator=Exists" \
  --set "tolerations[0].effect=NoSchedule"
```

&emsp;&emsp;Reference: https://docs.aws.amazon.com/eks/latest/userguide/aws-load-balancer-controller.html

### 5. Create storage class(es)
Auto Mode does not support the `kubernetes.io/aws-ebs` provisioner. Apply the provided storage class definitions, which use the Auto Mode compatible `ebs.csi.eks.amazonaws.com` provisioner:
```shell
kubectl apply -f storageclass-eks-auto.yaml
```

&emsp;&emsp;Reference: [storageclass-eks-auto.yaml](../../StorageClasses/AmazonEKS/storageclass-eks-auto.yaml)

Deploy ArcGIS Enterprise on Kubernetes
---
### 1. Populate deploy.properties file
Follow instructions from [Run the deployment script in silent mode](https://enterprise-k8s.arcgis.com/en/latest/deploy/run-the-deployment-script.htm#ESRI_SECTION1_930D8184D9E9480BB679ABED1743A8CE) in _Run the deployment script_.

Note: ArcGIS Enterprise uses application-level encryption and stores secrets as Kubernetes secrets. It does not have the functionality to integrate with secrets managers such as AWS Secrets Manager.

Note: `K8S_NAMESPACE` must match the `NAMESPACE` variable and `ARCGIS_SITENAME`/`CONTEXT` must match the `SITE_CONTEXT` variable exported in the "Set session variables" step.

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
LOAD_BALANCER_TYPE="aws-nlb-external"
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
### 1. If using Route53 for DNS: Create CNAME record to point to NLB service resource
```shell
DNSAlias=$(kubectl get secret arcgis-env-variables -n arcgis -o json | jq -r '.data["env-variables.json"]' | base64 -d | jq -r
'.ARCGIS_ENTERPRISE_FQDN')
NLB_DNS=$(kubectl get svc -n arcgis | grep LoadBalancer | awk '{print $4}')
aws route53 change-resource-record-sets --hosted-zone-id <hostedZoneID> --change-batch file://<(cat << EOF
{
  "Comment": "Create CNAME record for ArcGIS Enterprise on Kubernetes NLB",
  "Changes": [
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "${DNSAlias}",
        "Type": "CNAME",
        "TTL": 60,
        "ResourceRecords": [
          {
            "Value": "${NLB_DNS}"
          }
        ]
      }
    }
  ]
}
EOF
)
```

### 2. If using external DNS provider: Create CNAME record to point to NLB hostname
&emsp;a. Get NLB DNS alias
```shell
kubectl get svc -n arcgis | grep LoadBalancer | awk '{print $4}'
```

&emsp;b. Create CNAME record in DNS provider console (map deployment FQDN to NLB DNS alias)


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
RELATIONAL_STORAGE_CLASS="auto-ebs-sc"
RELATIONAL_STORAGE_LABEL_1=""
RELATIONAL_STORAGE_LABEL_2=""

# Object Store
OBJECT_STORAGE_TYPE="DYNAMIC"
OBJECT_STORAGE_SIZE="64Gi"
OBJECT_STORAGE_CLASS="auto-ebs-sc"
OBJECT_STORAGE_LABEL_1=""
OBJECT_STORAGE_LABEL_2=""

# In-Memory Store
MEMORY_STORAGE_TYPE="DYNAMIC"
MEMORY_STORAGE_SIZE="16Gi"
MEMORY_STORAGE_CLASS="auto-ebs-sc"
MEMORY_STORAGE_LABEL_1=""
MEMORY_STORAGE_LABEL_2=""

# Queue Store
QUEUE_STORAGE_TYPE="DYNAMIC"
QUEUE_STORAGE_SIZE="16Gi"
QUEUE_STORAGE_CLASS="auto-ebs-sc"
QUEUE_STORAGE_LABEL_1=""
QUEUE_STORAGE_LABEL_2=""

# Spatiotemporal and Index Store
INDEXER_STORAGE_TYPE="DYNAMIC"
INDEXER_STORAGE_SIZE="16Gi"
INDEXER_STORAGE_CLASS="auto-ebs-sc"
INDEXER_STORAGE_LABEL_1=""
INDEXER_STORAGE_LABEL_2=""

# Item Packages
SHARING_STORAGE_TYPE="DYNAMIC"
SHARING_STORAGE_SIZE="16Gi"
SHARING_STORAGE_CLASS="auto-ebs-sc"
SHARING_STORAGE_LABEL_1=""
SHARING_STORAGE_LABEL_2=""

# Prometheus (metrics api)
PROMETHEUS_STORAGE_TYPE="DYNAMIC"
PROMETHEUS_STORAGE_SIZE="30Gi"
PROMETHEUS_STORAGE_CLASS="auto-ebs-sc"
PROMETHEUS_STORAGE_LABEL_1=""
PROMETHEUS_STORAGE_LABEL_2=""

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


Verify the cluster
---
### 1. Verify storage and node scheduling resources
```shell
kubectl get storageclass
kubectl get nodeclass
kubectl get nodepools
```

### 2. Watch nodes join the cluster
```shell
kubectl get nodes -w
```

### 3. Verify add-ons and controllers
```shell
kubectl get pods -n kube-system
kubectl get pods -n kube-system -l app.kubernetes.io/name=aws-load-balancer-controller
aws eks list-pod-identity-associations \
  --cluster-name ${CLUSTER_NAME} \
  --region ${AWS_REGION}
```


Teardown
---
Use the following steps to delete all resources created by this guide in reverse order to avoid dependency errors during deletion.

### 1. Uninstall the AWS Load Balancer Controller
```shell
helm uninstall aws-load-balancer-controller -n kube-system
```

Delete the Kubernetes service account:
```shell
kubectl delete serviceaccount aws-load-balancer-controller -n kube-system
```

### 2. Delete the EKS cluster
Deleting the cluster automatically removes all NodePools, NodeClasses, add-ons, and pod identity associations:
```shell
aws eks delete-cluster \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION}
```

Wait for deletion to complete:
```shell
aws eks wait cluster-deleted \
  --name ${CLUSTER_NAME} \
  --region ${AWS_REGION}
```

### 3. Delete IAM roles
&emsp;a. Delete the cluster role and detach its policies
```shell
for POLICY_ARN in \
  "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSBlockStoragePolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSComputePolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSLoadBalancingPolicy" \
  "arn:aws:iam::aws:policy/AmazonEKSNetworkingPolicy"; do
  aws iam detach-role-policy \
    --role-name eks-automode-cluster-role-${CLUSTER_NAME} \
    --policy-arn "$POLICY_ARN"
done

aws iam delete-role --role-name eks-automode-cluster-role-${CLUSTER_NAME}
```

&emsp;b. Delete the node role and detach its policies
```shell
for POLICY_ARN in \
  "arn:aws:iam::aws:policy/AmazonEKSWorkerNodeMinimalPolicy" \
  "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"; do
  aws iam detach-role-policy \
    --role-name eks-automode-node-role-${CLUSTER_NAME} \
    --policy-arn "$POLICY_ARN"
done

aws iam delete-role --role-name eks-automode-node-role-${CLUSTER_NAME}
```

&emsp;c. Delete the pod identity roles
```shell
for ROLE in \
  AmazonEKSPodIdentityAmazonEBSCSIDriverRole-${CLUSTER_NAME} \
  AmazonEKSPodIdentityAmazonVPCCNIRole-${CLUSTER_NAME} \
  AmazonEKSPodIdentityAWSLoadBalancerControllerRole-${CLUSTER_NAME}; do
  ATTACHED=$(aws iam list-attached-role-policies --role-name "$ROLE" \
    --query 'AttachedPolicies[].PolicyArn' --output text)
  for POLICY_ARN in $ATTACHED; do
    aws iam detach-role-policy --role-name "$ROLE" --policy-arn "$POLICY_ARN"
  done
  aws iam delete-role --role-name "$ROLE"
done

aws iam delete-policy \
  --policy-arn arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy-${CLUSTER_NAME}
```

### 4. Delete the security group
```shell
aws ec2 delete-security-group \
  --group-id ${CLUSTER_SG_ID} \
  --region ${AWS_REGION}
```
