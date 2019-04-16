"""Creates a single GCP project with various configurable options.

This is a somewhat generic template for FireCloud project creation. It is a
child template meant to be called by firecloud-project.py.
"""
import copy
import re

def bucketed_list(l, bucket_size):
  """Breaks an input list into multiple lists with a certain bucket size.

  Arguments:
    l: A list of items
    bucket_size: The size of buckets to create.

  Returns:
    A list of lists, where each entry contains a subset of items from the input
    list.
  """
  n = max(1, bucket_size)
  return [l[i:i + n] for i in xrange(0, len(l), n)]


def create_apis(context):
  """Creates resources for API activation.

  Args:
      context: the DM context object.

  Returns:
    A list of DM resources to active the configured APIs.
  """
  apis = context.properties.get('activateApis', [])

  # Enable the storage-component API if the usage export, storage logs, or cromwell auth buckets are enabled.
  if ((context.properties.get('usageExportBucket') or
       context.properties.get('storageLogsBucket') or
       context.properties.get('cromwellAuthBucket')) and
      'storage-component.googleapis.com' not in apis):
    apis.append('storage-component.googleapis.com')

  resources = []

  # Activate APIs in batches of 20 at a time using the "batchEnable" service
  # usage API method. The magic number 20 is part of the batchEnable API
  # contract; see
  # https://cloud.google.com/service-usage/docs/reference/rest/v1/services/batchEnable.
  api_buckets = bucketed_list(apis, 20)

  for i in range(0, len(api_buckets)):
    api_names = api_buckets[i]

    resources.append({
        'name': 'api-{}'.format(i),
        'action': ('gcp-types/serviceusage-v1beta1:' +
                   'serviceusage.services.batchEnable'),
        'properties': {
            'parent': 'projects/$(ref.project.projectNumber)',
            'serviceIds': api_names,
        },
        'metadata': {
            # The only thing needed to activate APIs is billing to be enabled.
            'dependsOn': ['billing'],
        }
    })

  return resources


def create_iam_policies(context):
  """ Grant the shared project IAM permissions. """
  if 'iamPolicies' not in context.properties:
    return []

  return [
      {
          # Get the IAM policy first, so as not to remove
          # any existing bindings.
          'name': 'get-iam-policy',
          'action': ('gcp-types/cloudresourcemanager-v1:' +
                     'cloudresourcemanager.projects.getIamPolicy'),
          'properties': {
              'resource': '$(ref.project.projectId)'
          },
          'metadata': {
              'dependsOn': ['project'],
              'runtimePolicy': ['UPDATE_ALWAYS']
          }
      },
      {
          # Set the IAM policy patching the existing policy
          # with whatever is currently in the config.
          'name': 'patch-iam-policy',
          'action': ('gcp-types/cloudresourcemanager-v1:' +
                     'cloudresourcemanager.projects.setIamPolicy'),
          'properties': {
              'resource': '$(ref.project.projectId)',
              'policy': '$(ref.get-iam-policy)',
              'gcpIamPolicyPatch': {
                  'add': context.properties['iamPolicies']
              }
          },
          'metadata': {
              'dependsOn': ['get-iam-policy']
          }
      }
  ]


def create_usage_export_bucket(context, api_names_list):
  """Creates the usage export bucket.

  This bucket will be set up to collect compute engine usage data.

  We can't start creating GCS buckets until all project APIs are enabled, so we
  take the list of API-enablement resource names as a parameter to include in
  the dependency list of this resource.

  Args:
      context: the DM context object.
      api_names_list: the names of all resources that enable GCP APIs.

  Returns:
    A list of DM resources, to create and set the usage export bucket.
  """
  resources = []
  bucket_name = '$(ref.project.projectId)-usage-export'

  # Create the bucket.
  resources.append({
      'name': 'create-usage-export-bucket',
      'type': 'gcp-types/storage-v1:buckets',
      'properties': {
          'project': '$(ref.project.projectId)',
          'name': bucket_name
      },
      'metadata': {
          # Only create the bucket once all APIs have been
          # activated.
          'dependsOn': api_names_list
      }
  })

  # Set the project's usage export bucket.
  resources.append({
      'name': 'set-usage-export-bucket',
      'action': (
          'gcp-types/compute-v1:' + 'compute.projects.setUsageExportBucket'),
      'properties': {
          'project': '$(ref.project.projectId)',
          'bucketName': 'gs://' + bucket_name
      },
      'metadata': {
          'dependsOn': ['create-usage-export-bucket']
      }
  })

  return resources


def create_storage_logs_bucket(context, api_names_list):
    """Creates the storage logs bucket.

    This bucket will be set up to collect compute engine usage data.

    We can't start creating GCS buckets until all project APIs are enabled, so we
    take the list of API-enablement resource names as a parameter to include in
    the dependency list of this resource.

    Args:
        context: the DM context object.
        api_names_list: the names of all resources that enable GCP APIs.

    Returns:
      A list of DM resources, to create and set the storage logs bucket.
    """
    resources = []
    bucket_name = 'storage-logs-$(ref.project.projectId)'

    # Create the bucket.
    resources.append({
        'name': 'create-storage-logs-bucket',
        'type': 'gcp-types/storage-v1:buckets',
        'properties': {
            'project': '$(ref.project.projectId)',
            'name': bucket_name,
            'lifecycle': {
                'rule': [
                    {
                        'action': {
                            'type': 'Delete'
                        },
                        'condition': {
                            'age': context.properties.get('storageBucketLifecycle', 180)
                        }

                    }
                ]
            }
        },
        'metadata': {
            # Only create the bucket once all APIs have been
            # activated.
            'dependsOn': api_names_list
        }
    })

    # # Add cloud-storage-analytics@google.com as a writer so it can write logs
    # # Do it as a separate call so bucket gets default permissions plus this one
    resources.append({
        'name': 'add-cloud-storage-writer',
        'type': 'gcp-types/storage-v1:bucketAccessControls',
        'properties': {
            'bucket': bucket_name,
            'entity': 'group-cloud-storage-analytics@google.com',
            'role': 'WRITER'
        },
        'metadata': {
            # Only create the bucket once all APIs have been
            # activated.
            'dependsOn': ['create-storage-logs-bucket']
        }
    })

    return resources


def create_cromwell_auth_bucket(context, api_names_list):
    """Creates the cromwell auth bucket.

    This bucket will be set up to collect compute engine usage data.

    We can't start creating GCS buckets until all project APIs are enabled, so we
    take the list of API-enablement resource names as a parameter to include in
    the dependency list of this resource.

    Args:
        context: the DM context object.
        api_names_list: the names of all resources that enable GCP APIs.

    Returns:
      A list of DM resources, to create and set the cromwell auth bucket.
    """
    resources = []
    bucket_name = 'cromwell-auth-$(ref.project.projectId)'

    bucket_readers = [] # this should maybe be adjusted to be more extendable?
    if 'projectOwnersGroup' in context.properties:
        bucket_readers.append(context.properties.get('projectOwnersGroup'))

    if 'projectViewersGroup' in context.properties:
        bucket_readers.append(context.properties.get('projectViewersGroup'))

    bucket_acl = [
        {
            'type': 'gcp-types/storage-v1:bucketAccessControls',
            'properties': {
                'entity': 'project-editors-$(ref.project.projectNumber)',
                'role': 'OWNER'
            }
        },
        {
            'type': 'gcp-types/storage-v1:bucketAccessControls',
            'properties': {
                'entity': 'project-owners-$(ref.project.projectNumber)',
                'role': 'OWNER'
            }
        }
    ]

    default_object_acl = [
        {
            'type': 'gcp-types/storage-v1:objectAccessControls',
            'properties': {
                'entity': 'project-editors-$(ref.project.projectNumber)',
                'role': 'OWNER'
            }
        },
        {
            'type': 'gcp-types/storage-v1:objectAccessControls',
            'properties': {
                'entity': 'project-owners-$(ref.project.projectNumber)',
                'role': 'OWNER'
            }
        }
    ]

    for email in bucket_readers:
        bucket_acl.append({
            'type': 'gcp-types/storage-v1:bucketAccessControls',
            'properties': {
                'entity': 'group-{}'.format(email),
                'role': 'READER'
            }
        })

        default_object_acl.append({
            'type': 'gcp-types/storage-v1:objectAccessControls',
            'properties': {
                'entity': 'group-{}'.format(email),
                'role': 'READER'
            }
        })

    # Create the bucket.
    resources.append({
        'name': 'create-cromwell-auth-bucket',
        'type': 'gcp-types/storage-v1:buckets',
        'properties': {
            'project': '$(ref.project.projectId)',
            'name': bucket_name,
             'acl[]': bucket_acl,
             'defaultObjectAcl[]': default_object_acl
        },
        'metadata': {
            # Only create the bucket once all APIs have been
            # activated.
            'dependsOn': api_names_list
        }
    })

    return resources


def delete_default_network(api_names_list):
  """Creates DM actions to remove the default VPC network.

  Args:
      api_names_list: the names of all resources that enable GCP APIs.

  Returns:
      A list of DM actions to remove default firewall rules and the default VPC
      network.
  """
  # These are GCP's statically-named firewall rules that we need to delete from
  # the project before we delete the entire network.
  icmp_name = 'delete-default-allow-icmp'
  internal_name = 'delete-default-allow-internal'
  rdp_name = 'delete-default-allow-rdp'
  ssh_name = 'delete-default-allow-ssh'

  resource = [
      {
          'name': icmp_name,
          'action': 'gcp-types/compute-beta:compute.firewalls.delete',
          'metadata': {
              'dependsOn': api_names_list
          },
          'properties': {
              'firewall': 'default-allow-icmp',
              'project': '$(ref.project.projectId)',
          }
      },
      {
          'name': internal_name,
          'action': 'gcp-types/compute-beta:compute.firewalls.delete',
          'metadata': {
              'dependsOn': api_names_list
          },
          'properties': {
              'firewall': 'default-allow-internal',
              'project': '$(ref.project.projectId)',
          }
      },
      {
          'name': rdp_name,
          'action': 'gcp-types/compute-beta:compute.firewalls.delete',
          'metadata': {
              'dependsOn': api_names_list
          },
          'properties': {
              'firewall': 'default-allow-rdp',
              'project': '$(ref.project.projectId)',
          }
      },
      {
          'name': ssh_name,
          'action': 'gcp-types/compute-beta:compute.firewalls.delete',
          'metadata': {
              'dependsOn': api_names_list
          },
          'properties': {
              'firewall': 'default-allow-ssh',
              'project': '$(ref.project.projectId)',
          }
      },
  ]

  # Ensure all firewall rules are removed before deleting the VPC.
  network_dependency = copy.copy(api_names_list)
  network_dependency.extend([icmp_name, internal_name, rdp_name, ssh_name])

  resource.append({
      'name': 'delete-default-network',
      'action': 'gcp-types/compute-beta:compute.networks.delete',
      'metadata': {
          'dependsOn': network_dependency
      },
      'properties': {
          'network': 'default',
          'project': '$(ref.project.projectId)'
      }
  })

  return resource


def delete_default_service_account(api_names_list):
  """Deletes the default service account.

  Args:
      api_names_list: the names of all resources that enable GCP APIs.

  Returns:
      A list of DM actions to remove the default project service account.
  """

  resource = [{
      'name': 'delete-default-sa',
      'action': 'gcp-types/iam-v1:iam.projects.serviceAccounts.delete',
      'metadata': {
          'dependsOn': api_names_list,
          'runtimePolicy': ['CREATE']
      },
      'properties': {
          'name': ('projects/$(ref.project.projectId)/serviceAccounts/' +
                   '$(ref.project.projectNumber)-compute@' +
                   'developer.gserviceaccount.com'),
      }
  }]

  return resource


def label_safe_string(s, prefix = "fc-"):
  # https://cloud.google.com/compute/docs/labeling-resources#restrictions
  s = prefix + re.sub("[^a-z0-9\\-_]", "-", s.lower())
  return s[:63]

def generate_config(context):
  """Entry point, called by deployment manager.

  Arguments:
      context: the Deployment Manager context object.

  Returns:
      A list of resources to be consumed by the Deployment Manager.
  """

  project_id = context.properties.get('projectId')
  project_name = context.properties.get('name', project_id)
  project_labels = context.properties.get('labels', {})

  project_labels.update({
      "billingaccount": label_safe_string(context.properties.get('billingAccountFriendlyName'))
  })

  # Ensure that the parent ID is a string.
  context.properties['parent']['id'] = str(context.properties['parent']['id'])

  resources = [
      {
          'name': 'project',
          'type': 'cloudresourcemanager.v1.project',
          'properties': {
              'name': project_name,
              'projectId': project_id,
              'parent': context.properties['parent'],
              'labels': project_labels
          }
      },
      {
          'name': 'billing',
          'type': 'deploymentmanager.v2.virtual.projectBillingInfo',
          'properties': {
              'name':
                  'projects/$(ref.project.projectId)',
              'billingAccountName':
                  context.properties['billingAccountId']
          }
      }
  ]

  resources.extend(create_iam_policies(context))

  api_resources = create_apis(context)
  resources.extend(api_resources)
  api_resource_names = [resource['name'] for resource in api_resources]

  if context.properties.get('createUsageExportBucket', True):
    resources.extend(create_usage_export_bucket(context, api_resource_names))

  if context.properties.get('storageLogsBucket', True):
    resources.extend(create_storage_logs_bucket(context, api_resource_names))

  if context.properties.get('cromwellAuthBucket', True):
    resources.extend(create_cromwell_auth_bucket(context, api_resource_names))

  if context.properties.get('removeDefaultVPC', True):
    resources.extend(delete_default_network(api_resource_names))

  if context.properties.get('removeDefaultSA', True):
    resources.extend(delete_default_service_account(api_resource_names))

  return {
      'resources':
          resources,
      'outputs': [
          {
              'name': 'projectId',
              'value': '$(ref.project.projectId)'
          },
          {
              'name': 'usageExportBucketName',
              'value': '$(ref.project.projectId)-usage-export'
          },
          {
              'name': 'storageLogsBucketName',
              'value': 'storage-logs-$(ref.project.projectId)'
          },
          {
              'name': 'cromwellAuthBucketName',
              'value': 'cromwell-auth-$(ref.project.projectId)'
          },
          {
              'name': 'resourceNames',
              'value': [resource['name'] for resource in resources]
          },
      ]
  }
