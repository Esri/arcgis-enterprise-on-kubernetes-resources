
# Storage classes

For each provider, two storage class example YAMLs are provided:
1. For all statefulsets created during organization creation, the reclaimPolicy should be set to *Delete* for the specified storage class. This setting is default for the majority of pre-configured storage classes in each provider.
2. In order to facilitate recovery of an organization if the existing organization is no longer available, any registered hosted backup store should use the *Retain* reclaimPolicy.
