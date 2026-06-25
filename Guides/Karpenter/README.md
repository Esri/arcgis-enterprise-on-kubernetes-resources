Karpenter for ArcGIS Enterprise on Kubernetes
===
Table of contents
---
  * [What is Karpenter?](#what-is-karpenter)
  * [How Karpenter works](#how-karpenter-works)
  * [NodePools and NodeClasses](#nodepools-and-nodeclasses)
  * [Supported and not supported in this release](#what-karpenter-is---and-is-not---supported-in-arcgis-enterprise-on-kubernetes-121-release)
  * [Deployment guides](#deployment-guides)
  * [Official documentation](#official-documentation)

What is Karpenter?
---
Karpenter is an open-source Kubernetes node lifecycle controller that provisions compute capacity in response to unschedulable pods. Instead of relying on pre-created node groups, infrastructure is launched on demand based on what workloads request.

Major cloud providers deliver managed implementations of Karpenter, removing the need to deploy and operate the controller yourself:

- **Amazon Web Services**: available through Amazon Elastic Kubernetes Service (EKS) Auto Mode

- **Microsoft Azure**: available through Azure Kubernetes Service Node Auto Provisioning (NAP)

How Karpenter works
---
### 1. Pod scheduling
When new workloads are deployed, Kubernetes first attempts to schedule pods onto existing nodes.

### 2. Unschedulable detection
If pods cannot be placed due to insufficient resources, they remain in a pending state. Karpenter watches for these pods.

### 3. Node provisioning
Karpenter evaluates the CPU, memory, GPU, and other requirements declared in each pod's resource requests, selects the most suitable instance type, and provisions nodes just in time.

### 4. Capacity consolidation
Karpenter continuously monitors cluster utilization and reclaims nodes that are empty or underutilized, reducing idle compute cost.

NodePools and NodeClasses
---
Karpenter uses two custom resources to control provisioning behavior.

### NodePools define what and when
NodePools specify which instance families, CPU and memory ranges, labels, taints, and disruption policies apply to a group of nodes. Each NodePool acts as a policy boundary: only pods that match the NodePool's requirements are placed on nodes it manages.

### NodeClasses define how and where
NodeClasses contain cloud-specific configuration: machine images or AMIs, storage settings, networking, and security. The specific resource kind varies by provider: `EC2NodeClass` on EKS Auto Mode, `AKSNodeClass` on AKS NAP.

Together, a NodePool and its associated NodeClass form a template that guides Karpenter's node selection and launch decisions.

## Karpenter features supported in ArcGIS Enterprise 12.1 on Kubernetes release
---
Understanding Karpenter's capabilities and limitations is critical for successful deployment and operation. This section outlines what Karpenter features are supported for ArcGIS Enterprise workloads, and which are not recommended in this release.

### Supported: node autoscaling

Karpenter is supported and recommended for **elastic compute scaling**:

* Provisioning new nodes when pending ArcGIS pods cannot be scheduled on existing capacity
* Reclaiming empty or underutilized nodes when demand decreases
* Directing workloads to right-sized instance types based on pod resource requests
* Isolating stateful data store pods from general-purpose workloads via dedicated NodePools

### Not supported in this release: automated node image rotation

Karpenter's **drift** feature can automatically detect when a node is running an outdated AMI or VM image and replace it. **This feature is not recommended for ArcGIS Enterprise and must be disabled.**

ArcGIS Enterprise runs long-duration operations that are not safe to interrupt:

* **Tile cache generation**: can run continuously for days or weeks on large map extents
* **Raster analysis jobs**: may span hours to days depending on dataset size
* **Geoprocessing services**: can execute long-running spatial operations

When Karpenter replaces a node, it cordons and drains the node, terminating all pods running on it. Any ArcGIS job in flight on that node is killed and does not automatically resume. Because these jobs can run at any time and their duration is unpredictable, no safe automated maintenance window can be defined.

**Until a future release that integrates job-state awareness into the rotation workflow, node image updates must be performed manually.**

### Manual node rotation procedure

Before rotating worker nodes, enable read-only mode in ArcGIS Enterprise Manager:

>[!Note]
> You can check if there is an ami update available by running the below command `kubectl get nodeclaims -o custom-columns="NAME:.metadata.name,DRIFTED:.status.conditions[?(@.type=='Drifted')].status,REASON:.status.conditions[?(@.type=='Drifted')].reason"`. If there is an update available, the Drifted column will show True and the Reason column will show OutdatedAMI. If there are no updates available, the Drifted column will show False.

1. [Enable read-only mode](https://doc.esri.com/en/arcgis-enterprise-k8s/12.1/administer/enable-read-only-mode.html) to prevent new jobs from starting.
2. Make sure no jobs are actively running
3. In the terminal/shell connected to your cluster, cordon and drain all worker nodes to gracefully evict pods and prevent new ones from scheduling there:
   ```
   kubectl cordon <node-name>
   kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
   ```
4. Karpenter will detect the unschedulable pods and provision new nodes as needed. Monitor the cluster until all workloads are running on the new nodes and no pending pods remain.

5. Once the new nodes are fully operational and all workloads have been migrated, karpenter will automatically deprovision the old nodes. You can verify this by checking the node status:
   ```
   kubectl get nodes
   ```
6. After the old nodes have been removed, disable Read only mode in ArcGIS Enterprise Manager to resume normal operations:
   ```
   Enterprise Manager → Settings → Read-only mode → Disable Read-only mode
   ```

7. Monitor the cluster for any issues and ensure all workloads are running smoothly on the new nodes.

Deployment guides
---
### Amazon EKS Auto Mode
Follow the step-by-step guide to create an EKS Auto Mode cluster, configure NodePools and NodeClasses, set up workload identity, and deploy ArcGIS Enterprise on Kubernetes.

&emsp;&emsp;[Amazon EKS Auto Mode Deployment Guide](../../aws/amazon-eks-automode-deployment-guide.md)

### Azure AKS Node Auto Provisioning
Follow the step-by-step guide to create an AKS cluster with Node Auto Provisioning enabled, configure NodePools and NodeClasses, set up workload identity, and deploy ArcGIS Enterprise on Kubernetes.

&emsp;&emsp;[Azure AKS Node Auto Provisioning Deployment Guide](../../azure/azure-nap-deployment-guide.md)

Official documentation
---
* Karpenter: https://karpenter.sh
* Amazon EKS Auto Mode: https://docs.aws.amazon.com/eks/latest/userguide/automode.html
* Azure AKS Node Auto Provisioning: https://learn.microsoft.com/azure/aks/node-autoprovision
* ArcGIS Enterprise on Kubernetes system requirements: https://enterprise-k8s.arcgis.com/en/latest/deploy/system-requirements.htm
* ArcGIS Enterprise on Kubernetes administration: https://enterprise-k8s.arcgis.com/en/latest/administer/administer-overview.htm
