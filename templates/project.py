# Copyright 2018 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
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
"""
This template creates a single project with the specified service
accounts and APIs enabled.
"""
import copy

def GenerateConfig(context):
    """ Entry point for the deployment resources. """

    project_id = context.properties.get('projectId')
    project_name = context.properties.get('name', project_id)

    # Ensure that the parent ID is a string.
    context.properties['parent']['id'] = str(context.properties['parent']['id'])

    resources = [
        {
            'name': 'project',
            'type': 'cloudresourcemanager.v1.project',
            'properties':
                {
                    'name': project_name,
                    'projectId': project_id,
                    'parent': context.properties['parent']
                }
        },
        {
            'name': 'billing',
            'type': 'deploymentmanager.v2.virtual.projectBillingInfo',
            'properties':
                {
                    'name':
                        'projects/$(ref.project.projectId)',
                    'billingAccountName':
                        'billingAccounts/' +
                        context.properties['billingAccountId']
                }
        }
    ]

    resources.extend(create_iam_policies(context))

    api_resources = activate_apis(context)
    api_resource_names = [resource['name'] for resource in api_resources]
    resources.extend(api_resources)
    resources.extend(create_bucket(context, api_resource_names))

    if context.properties.get('removeDefaultVPC', True):
        resources.extend(delete_default_network(api_resource_names))

    if context.properties.get('removeDefaultSA', True):
        resources.extend(delete_default_service_account(api_resource_names))

    return {
        'resources':
            resources,
        'outputs':
            [
                {
                    'name': 'projectId',
                    'value': '$(ref.project.projectId)'
                },
                {
                    'name': 'usageExportBucketName',
                    'value': '$(ref.project.projectId)-usage-export'
                },
                {
                    'name': 'resourceNames',
                    'value': [resource['name'] for resource in resources]
                }
            ]
    }

def bucketed_list(l, bucket_size):
  """Breaks an input list into multiple lists with a certain bucket size."""
  n = max(1, bucket_size)
  return [l[i:i+n] for i in xrange(0, len(l), n)]


def activate_apis(context):
    """Generates resources for API activation. """
    apis = context.properties.get('activateApis', [])

    # Enable the storage-component API if the usage export bucket is enabled.
    if (
        context.properties.get('usageExportBucket') and
        'storage-component.googleapis.com' not in apis
    ):
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
          'action': (
              'gcp-types/serviceusage-v1beta1:' +
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
            'action': 'gcp-types/cloudresourcemanager-v1:cloudresourcemanager.projects.getIamPolicy', # pylint: disable=line-too-long
            'properties': {
                'resource': '$(ref.project.projectId)'
            },
            'metadata':
                {
                    'dependsOn': ['project'],
                    'runtimePolicy': ['UPDATE_ALWAYS']
                }
        },
        {
            # Set the IAM policy patching the existing policy
            # with whatever is currently in the config.
            'name': 'patch-iam-policy',
            'action': 'gcp-types/cloudresourcemanager-v1:cloudresourcemanager.projects.setIamPolicy', # pylint: disable=line-too-long
            'properties':
                {
                    'resource': '$(ref.project.projectId)',
                    'policy': '$(ref.get-iam-policy)',
                    'gcpIamPolicyPatch':
                        {
                            'add': context.properties['iamPolicies']
                        }
                },
            'metadata': {
              'dependsOn': ['get-iam-policy']
            }
        }
    ]


def create_bucket(context, api_names_list):
    """ Resources for the usage export bucket. """
    resources = []
    if context.properties.get('usageExportBucket'):
        bucket_name = '$(ref.project.projectId)-usage-export'

        # Create the bucket.
        resources.append(
            {
                'name': 'create-usage-export-bucket',
                'type': 'gcp-types/storage-v1:buckets',
                'properties':
                    {
                        'project': '$(ref.project.projectId)',
                        'name': bucket_name
                    },
                'metadata':
                    {
                        # Only create the bucket once all APIs have been
                        # activated.
                        'dependsOn': api_names_list
                    }
            }
        )

        # Set the project's usage export bucket.
        resources.append(
            {
                'name':
                    'set-usage-export-bucket',
                'action':
                    'gcp-types/compute-v1:compute.projects.setUsageExportBucket',  # pylint: disable=line-too-long
                'properties':
                    {
                        'project': '$(ref.project.projectId)',
                        'bucketName': 'gs://' + bucket_name
                    },
                'metadata': {
                    'dependsOn': ['create-usage-export-bucket']
                }
            }
        )

    return resources


def delete_default_network(api_names_list):
    """ Delete the default network. """

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
            'properties':
                {
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
            'properties':
                {
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
            'properties':
                {
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
            'properties':
                {
                    'firewall': 'default-allow-ssh',
                    'project': '$(ref.project.projectId)',
                }
        }
    ]

    # Ensure the firewall rules are removed before deleting the VPC.
    network_dependency = copy.copy(api_names_list)
    network_dependency.extend([icmp_name, internal_name, rdp_name, ssh_name])

    resource.append(
        {
            'name': 'delete-default-network',
            'action': 'gcp-types/compute-beta:compute.networks.delete',
            'metadata': {
                'dependsOn': network_dependency
            },
            'properties':
                {
                    'network': 'default',
                    'project': '$(ref.project.projectId)'
                }
        }
    )

    return resource


def delete_default_service_account(api_names_list):
    """ Delete the default service account. """

    resource = [
        {
            'name': 'delete-default-sa',
            'action': 'gcp-types/iam-v1:iam.projects.serviceAccounts.delete',
            'metadata':
            {
                    'dependsOn': api_names_list,
                    'runtimePolicy': ['CREATE']
                },
            'properties':
                {
                    'name':
                        'projects/$(ref.project.projectId)/serviceAccounts/$(ref.project.projectNumber)-compute@developer.gserviceaccount.com'  # pylint: disable=line-too-long
                }
        }
    ]

    return resource
